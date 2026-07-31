"""Managers for v2 PRD/FSD/TDD-side document commands."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .chunk_parser import Chunk, parse_file, parse_text
from .index_manager import IndexManager
from .new_model_validator import check_edge_write, normalize_target_file, scan_content_relations
from .specgraph import combined_specgraph, combined_view, load_specgraph, resolve_chunk_uri, specgraph_path, sync_specgraph
from .schemas import DiscussionUsage
from .validator import ValidationError, ValidationIssue
from .version_manager import VersionManager

TARGET_FILE_RE = re.compile(r"^\s*target_file:\s*(\S+)\s*$", re.MULTILINE)
NEW_MODEL_RELS = {"derives", "decomposes", "details", "depends_on"}


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
    target_file_content: str | None = None


class NewModelManager:
    def __init__(self, project_root: Path):
        self.root = project_root.resolve()
        self.versions = VersionManager(self.root)
        self.indexes = IndexManager(self.root)

    def _require_phase(self, version: str, allowed: tuple[str, ...], code: str, op: str):
        """P7 top-down gate (收 strict mode): reject an entry-point call whose
        version phase is not one of ``allowed`` — zero-write, retryable. A
        missing version → VERSION_NOT_FOUND (it must be created first; no
        auto-create). Layers only advance prd→fsd→tdd when the parent layer is
        confirmed; ``revert`` steps a layer back, ``version revert`` escapes."""
        if not self.versions.version_meta_path(version).exists():
            raise _validation_error(
                "VERSION_NOT_FOUND",
                f"version {version} does not exist — run `version create` first",
                version,
            )
        meta = self.versions.load_version_meta(version)
        phase = meta.phase or "empty"
        if phase not in allowed:
            raise _validation_error(
                code,
                f"{op} requires version phase in {list(allowed)}, current: {phase}",
                version,
            )
        return meta

    def _discussion_intent(
        self,
        *,
        layer: str,
        target_id: str,
        parent_id: str | None,
        file: str | None,
        action: str,
        overrides: str | None,
        operation: str,
    ) -> dict[str, str | None]:
        normalized_file = _validated_index_path(file, layer) if file else f"{layer}/{target_id}"
        return {
            "protocol": "ctx-v1",
            "layer": layer,
            "target": target_id,
            "parent": parent_id,
            "file": normalized_file,
            "action": action,
            "overrides": overrides,
            "operation": operation,
        }

    @staticmethod
    def _context_token(intent: dict[str, str | None], background: dict) -> str:
        payload = json.dumps(
            {"intent": intent, "background": background},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"ctx-v1.{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"

    def _validate_context(
        self,
        *,
        version: str,
        layer: str,
        target_id: str,
        parent_id: str | None,
        file: str | None,
        action: str,
        overrides: str | None,
        operation: str,
        context_token: str | None,
        skip_context: bool,
    ) -> DiscussionUsage:
        if context_token is not None and skip_context:
            raise _validation_error(
                "CONTEXT_TOKEN_CONFLICT",
                "--context-token and --skip-context are mutually exclusive",
                target_id,
            )
        if skip_context:
            return DiscussionUsage(mode="skipped")
        if context_token is None:
            raise _validation_error(
                "CONTEXT_TOKEN_REQUIRED",
                "content writes require a matching context token or --skip-context",
                target_id,
            )
        if re.fullmatch(r"ctx-v1\.[0-9a-f]{64}", context_token) is None:
            raise _validation_error("CONTEXT_TOKEN_INVALID", "invalid context token format", target_id)
        background = self.prepare_discussion(
            version,
            layer,
            target_id,
            parent_id=parent_id,
            file=file,
            action=action,
            overrides=overrides,
            operation=operation,
        )
        expected = background["context_token"]
        if context_token != expected:
            raise _validation_error(
                "CONTEXT_TOKEN_STALE",
                "context token no longer matches the current background or write intent",
                target_id,
            )
        return DiscussionUsage(mode="receipt", receipt_digest=f"sha256:{context_token.removeprefix('ctx-v1.')}")

    def _compose_fsd_content(
        self,
        version: str,
        file: str,
        target_chunk_id: str,
        content: str,
    ) -> tuple[str, set[str]]:
        """Overlay an FSD write onto its baseline and current version file.

        A split-level modify replaces only its named split. A root-level write
        retains the existing full-file behavior so legacy callers that replay a
        complete FSD file remain compatible.
        """
        incoming = parse_text(content, file=file)
        if not any(chunk.id == target_chunk_id for chunk in incoming.chunks):
            raise _validation_error(
                "ROOT_CHUNK_REQUIRED",
                f"FSD markdown must include target chunk {target_chunk_id}",
                target_chunk_id,
            )

        changed_ids = (
            {chunk.id for chunk in incoming.chunks}
            if ":" not in target_chunk_id
            else {target_chunk_id}
        )
        incoming_chunks = [chunk for chunk in incoming.chunks if chunk.id in changed_ids]
        sources = []
        baseline_path = self.indexes.find_baseline_file(file)
        if baseline_path is not None:
            sources.append(parse_file(baseline_path, self.root / "docs"))
        version_path = self.indexes.find_version_file(version, file)
        if version_path is not None:
            sources.append(parse_file(version_path, self.versions.versions_dir / version))

        chunks_by_id: dict[str, Chunk] = {}
        order: list[str] = []
        header = ""
        for parsed in sources:
            if not header and parsed.file_header:
                header = parsed.file_header
            for chunk in parsed.chunks:
                if chunk.id not in chunks_by_id:
                    order.append(chunk.id)
                chunks_by_id[chunk.id] = chunk
        if not header:
            header = incoming.file_header
        for chunk in incoming_chunks:
            if chunk.id not in chunks_by_id:
                order.append(chunk.id)
            chunks_by_id[chunk.id] = chunk

        parts = [header.rstrip()] if header.strip() else []
        parts.extend(chunks_by_id[chunk_id].content for chunk_id in order)
        return "\n\n".join(parts).rstrip() + "\n", changed_ids

    def create_fsd(
        self,
        version: str,
        root_chunk_id: str,
        content: str,
        *,
        file: str | None = None,
        action: str = "add",
        overrides: str | None = None,
        parent_chunk_id: str | None = None,
        context_token: str | None = None,
        skip_context: bool = False,
        _context_parent_id: str | None = None,
        _operation: str = "create",
    ) -> DocumentCreateResult:
        self._require_phase(
            version, ("prd-confirm", "fsd-creating"), "PRD_NOT_CONFIRMED", "fsd create"
        )
        file = _validated_index_path(file, "fsd") if file else f"fsd/{root_chunk_id}"
        if parent_chunk_id is not None:
            self._precheck_derives_parent(version, parent_chunk_id, root_chunk_id)

        effective_content, changed_ids = self._compose_fsd_content(
            version, file, root_chunk_id, content
        )
        owner_root = _parent_chunk_id(root_chunk_id)
        declared = self._parse_depends_on_declarations(owner_root, effective_content)
        prefix = f"{owner_root}:"
        view_before = combined_view(self.root, version)
        hydrated: dict[str, list[str]] = {}
        for cid in view_before.nodes:
            if cid.startswith(prefix) and cid not in declared:
                deps = [edge.dst for edge in view_before.edges_from(cid, "depends_on")]
                if deps:
                    hydrated[cid] = deps
        clean_content = _strip_depends_on_blocks(effective_content)
        result = self._create_document(
            version,
            root_chunk_id,
            clean_content,
            kind="fsd",
            file=file,
            action=action,
            overrides=overrides,
            parent_id=_context_parent_id if _context_parent_id is not None else parent_chunk_id,
            operation=_operation,
            context_token=context_token,
            skip_context=skip_context,
            index_chunk_ids=changed_ids,
        )
        final_deps = {**hydrated, **declared}
        self._reconcile_sibling_depends_on(version, owner_root, final_deps)
        derives_declared = self._parse_derives_declarations(owner_root, effective_content)
        derives_hydrated: dict[str, list[str]] = {}
        for cid in view_before.nodes:
            if cid.startswith(prefix) and cid not in derives_declared:
                deps = [edge.src for edge in view_before.edges_to(cid, "derives")]
                if deps:
                    derives_hydrated[cid] = deps
        final_derives = {**derives_hydrated, **derives_declared}
        self._reconcile_sibling_derives(version, owner_root, final_derives)
        if parent_chunk_id is not None:
            self._add_edge(version, parent_chunk_id, root_chunk_id, "derives")
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

        for src, dsts in declared.items():
            src_uri = uri_by_chunk.get(src) or resolve_chunk_uri(self.root, src, version)
            for dst in dsts:
                dst_uri = uri_by_chunk.get(dst) or resolve_chunk_uri(self.root, dst, version)
                graph.add_edge(
                    src_uri, dst_uri, "depends_on",
                    metadata={"source": "fsd-declaration"},
                )
        graph.save(specgraph_path(self.root, version))

    def _parse_derives_declarations(
        self, root_chunk_id: str, content: str
    ) -> dict[str, list[str]]:
        """Parse each split's declared PRD-requirement derives.

        Targets must be full PRD chunk ids (``[PRD]-...``). Rejection before write.
        """
        parsed = parse_text(content, file=f"fsd/{root_chunk_id}")
        prefix = f"{root_chunk_id}:"
        declared: dict[str, list[str]] = {}
        for chunk in parsed.chunks:
            if not chunk.id.startswith(prefix):
                continue
            names = _split_derives(chunk.content)
            if names is None:
                continue
            resolved: list[str] = []
            for name in names:
                if not name.startswith("[PRD]-"):
                    raise _validation_error(
                        "DERIVES_NOT_PRD",
                        f"{chunk.id} derives target {name} is not a PRD chunk (must start with [PRD]-)",
                        chunk.id,
                    )
                if name not in resolved:
                    resolved.append(name)
            # v2.63: FSD split → PRD requirement derives is M:N (a split may
            # derive from multiple PRD requirement chunks); only the PRD
            # root → FSD root edge (born via --parent, not this declaration
            # path) remains 1:1.
            declared[chunk.id] = resolved
        return declared

    def _reconcile_sibling_derives(
        self, version: str, root_chunk_id: str, declared: dict[str, list[str]]
    ) -> None:
        """Owned-scope reconcile for derives edges (same pattern as depends_on)."""
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

        # declared maps fsd_split_id -> [prd_chunk, ...]; the edge itself is
        # PRD (src) -> FSD split (dst) — the same direction as the
        # --parent-born root derives edge. Drop existing derives edges whose
        # dst is one of this file's splits before re-adding from ``declared``.
        graph.edges = [
            e for e in graph.edges
            if not (e.rel == "derives" and _endpoint_chunk_id(e.dst).startswith(prefix))
        ]
        uri_by_chunk = {spec.chunk_id: spec.uri for spec in graph.specs.values()}

        for fsd_split, prd_chunks in declared.items():
            dst_uri = uri_by_chunk.get(fsd_split) or resolve_chunk_uri(
                self.root, fsd_split, version
            )
            for prd_chunk in prd_chunks:
                # A declaration may reference an unchanged baseline PRD.  Its
                # endpoint must retain the baseline URI rather than inventing
                # a version URI with no matching Spec node.
                src_uri = uri_by_chunk.get(prd_chunk) or resolve_chunk_uri(
                    self.root, prd_chunk, version
                )
                graph.add_edge(
                    src_uri, dst_uri, "derives",
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
        context_token: str | None = None,
        skip_context: bool = False,
    ) -> EdgeCreateResult:
        """FSD "split-is-edge" entry — the retirement path of ``fsd link``.

        Parent-side gate is front-loaded (before any write) so a rejection
        leaves zero on disk; then the child FSD is written atomically (when
        ``content`` is given) and the decomposes edge is created through the
        full write-time gate. rel is always ``decomposes`` (details belongs to
        the tdd layer).
        """
        # P7 收: decompose is an FSD-layer op — requires PRD confirmed / FSD open.
        self._require_phase(
            version, ("prd-confirm", "fsd-creating"), "PRD_NOT_CONFIRMED", "fsd decompose"
        )
        view = combined_view(self.root, version)
        self._precheck_decompose_parent(view, parent_chunk_id, child_root_chunk_id)
        if content is not None:
            self.create_fsd(
                version,
                child_root_chunk_id,
                content,
                file=file,
                context_token=context_token,
                skip_context=skip_context,
                _context_parent_id=parent_chunk_id,
                _operation="decompose",
            )
        edge = self._add_edge(version, parent_chunk_id, child_root_chunk_id, "decomposes")
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
        # v2.52: decompose is FSD-internal only. PRD→FSD is a derives relation
        # (via `fsd create --parent`), not decompose.
        if parent.type == "prd":
            raise _validation_error(
                "INVALID_DECOMPOSES_TYPES",
                f"PRD {parent_chunk_id} does not decompose — use `fsd create --parent` (derives)",
                parent_chunk_id,
            )

    def _precheck_derives_parent(self, version: str, parent_chunk_id: str, child_id: str) -> None:
        """Parent-side derives gate (v2.52): parent must be a PRD in the view and
        must not already derive a different FSD (invariant ①, 1:1). Evaluable
        before the child FSD is written."""
        view = combined_view(self.root, version)
        parent = view.node(parent_chunk_id)
        if parent is None:
            raise _validation_error(
                "MISSING_ENDPOINT",
                f"derives parent {parent_chunk_id} not in graph",
                parent_chunk_id,
            )
        others = [
            e.dst for e in view.edges_from(parent_chunk_id, "derives")
            if e.dst != child_id
        ]
        if others:
            raise _validation_error(
                "PRD_FSD_LINK_NOT_UNIQUE",
                f"PRD {parent_chunk_id} already derives {others}",
                parent_chunk_id,
            )

    def confirm_fsd_layer(self, version: str) -> dict:
        """Freeze the FSD layer: lock [FSD]- chunks, phase → fsd-confirm."""
        self._require_phase(version, ("fsd-creating",), "FSD_LAYER_NOT_OPEN", "fsd confirm")
        idx = self.indexes.load_version_index(version)
        fsd_ids = [c.id for c in idx.chunks if c.id.startswith("[FSD]-")]
        if not fsd_ids:
            raise _validation_error(
                "NO_FSD_CHUNKS", f"version {version} has no FSD chunks", version
            )
        for entry in (chunk for chunk in idx.chunks if chunk.id.startswith("[FSD]-")):
            path = self.indexes.find_version_file(version, entry.file)
            if path is None:
                raise _validation_error(
                    "VERSION_INDEX_SOURCE_MISSING",
                    f"version index chunk {entry.id} has no source file {entry.file}",
                    entry.id,
                )
            parsed = parse_file(path, self.versions.versions_dir / version)
            if not any(chunk.id == entry.id for chunk in parsed.chunks):
                raise _validation_error(
                    "VERSION_INDEX_SOURCE_MISSING",
                    f"version index chunk {entry.id} is absent from {entry.file}",
                    entry.id,
                )
        working = [
            c.id for c in idx.chunks
            if c.id.startswith("[FSD]-") and c.state == "working"
        ]
        # v2.64: same ordering fix as confirm_prd_layer — persist phase first.
        meta = self.versions.load_version_meta(version)
        meta.phase = "fsd-confirm"
        self.versions.save_version_meta(meta)
        if working:
            self.versions.stage(version, working)
            self.versions.commit(version, "fsd layer confirm")
        else:
            self.versions._refresh_state(version)
        self.versions._git_commit(f"AIT {version} fsd-confirm")
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
        context_token: str | None = None,
        skip_context: bool = False,
    ) -> DocumentCreateResult:
        # P7 收: TDD layer requires the FSD layer confirmed (phase fsd-confirm)
        # or the TDD layer already open (tdd-creating).
        self._require_phase(
            version, ("fsd-confirm", "tdd-creating"), "FSD_NOT_CONFIRMED", "tdd create"
        )
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
            parent_id=parent_chunk_id,
            operation="create",
            context_token=context_token,
            skip_context=skip_context,
        )
        if parent_chunk_id is not None:
            self._add_edge(version, parent_chunk_id, root_chunk_id, "details")
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
        self._require_phase(version, ("tdd-creating",), "TDD_LAYER_NOT_OPEN", "tdd confirm")
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
        # v2.64: same ordering fix as confirm_prd_layer — persist phase first.
        meta = self.versions.load_version_meta(version)
        meta.phase = "tdd-confirm"
        self.versions.save_version_meta(meta)
        if working:
            self.versions.stage(version, working)
            self.versions.commit(version, "tdd layer confirm")
        else:
            self.versions._refresh_state(version)
        self.versions._git_commit(f"AIT {version} tdd-confirm")
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
        context_token: str | None = None,
        skip_context: bool = False,
    ) -> DocumentCreateResult:
        # P7 收: PRD layer must be open — a fresh version (empty) or still
        # authoring PRD (prd-creating). Past that, `prd revert` re-opens it.
        self._require_phase(
            version, ("empty", "prd-creating"), "PRD_LAYER_CLOSED", "prd create"
        )
        result = self._create_document(
            version,
            root_chunk_id,
            content,
            kind="prd",
            file=file,
            action=action,
            overrides=overrides,
            parent_id=None,
            operation="create",
            context_token=context_token,
            skip_context=skip_context,
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
        self._require_phase(version, ("prd-creating",), "PRD_LAYER_NOT_OPEN", "prd confirm")
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
        # v2.64: persist the new phase BEFORE stage/commit so that commit()'s
        # internal _refresh_state (triggered via VersionManager.commit) reads
        # the already-updated phase — otherwise the tracked state.md lags one
        # phase behind right after confirm.
        meta = self.versions.load_version_meta(version)
        meta.phase = "prd-confirm"
        self.versions.save_version_meta(meta)
        if working:
            self.versions.stage(version, working)
            self.versions.commit(version, "prd layer confirm")
        else:
            self.versions._refresh_state(version)
        self.versions._git_commit(f"AIT {version} prd-confirm")
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

    def _add_edge(self, version: str, src: str, dst: str, rel: str) -> EdgeCreateResult:
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
        # P7 收: codegen on an active version requires the TDD layer confirmed.
        # (version=None or a merged/absent version → baseline codegen, no gate.)
        if version is not None and self.versions.version_meta_path(version).exists():
            self._require_phase(version, ("tdd-confirm",), "TDD_NOT_CONFIRMED", "codegen")
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

        # v2.60: read target_file current content so the AI has spec + code together.
        target_file_content: str | None = None
        if target_file:
            try:
                tf_path = self.root.parent / target_file
                target_file_content = tf_path.read_text(encoding="utf-8")
            except Exception:
                pass  # file absent or unreadable — bundle still valid

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
            target_file_content=target_file_content,
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
        for edge in sorted(view.edges_to(root_chunk_id, "decomposes"), key=lambda item: item.src):
            src = view.node(edge.src)
            if src is None or src.chunk_id in seen:
                continue
            self._append_context_item(items, seen, src)
            if src.type == "fsd" and ":" in src.chunk_id:
                parent_root = view.node(_parent_chunk_id(src.chunk_id))
                if parent_root is not None and parent_root.chunk_id not in seen:
                    self._append_context_item(items, seen, parent_root)
                    self._walk_upstream_roots(view, parent_root.chunk_id, items, seen)
        # v2.52: an FSD tree root traces up to its PRD via a derives edge.
        for edge in sorted(view.edges_to(root_chunk_id, "derives"), key=lambda item: item.src):
            src = view.node(edge.src)
            if src is None or src.chunk_id in seen:
                continue
            self._append_context_item(items, seen, src)

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

    def prepare_discussion(
        self,
        version: str,
        layer: str,
        target_id: str,
        parent_id: str | None = None,
        *,
        file: str | None = None,
        action: str = "add",
        overrides: str | None = None,
        operation: str = "create",
    ) -> dict:
        """v2.53 迭代连续性: assemble the discussion background for a layer's
        create — 现状(经关联检索) + 修改方向(上层已落地的改动) → 讨论出新 chunk.

        Zero-write, phase untouched; gated by the same layer phase as the write
        path. Two shapes:
        - 发现式 (no parent_id): anchors = this version's upper-layer changed
          chunks; related = one-hop neighbours of each anchor (combined view).
        - 锚定式 (parent_id given): anchor = the named parent chunk; linked =
          all its adjacent chunks; upstream = its chain up to the PRD.
        Empty baseline → empty background (初始 = 现状为空的迭代, zero branch).
        """
        gates = {
            "prd": (("empty", "prd-creating"), "PRD_LAYER_CLOSED", "prd create"),
            "fsd": (("prd-confirm", "fsd-creating"), "PRD_NOT_CONFIRMED", "fsd create"),
            "tdd": (("fsd-confirm", "tdd-creating"), "FSD_NOT_CONFIRMED", "tdd create"),
        }
        allowed, code, op = gates[layer]
        self._require_phase(version, allowed, code, op)
        view = combined_view(self.root, version)

        intent = self._discussion_intent(
            layer=layer,
            target_id=target_id,
            parent_id=parent_id,
            file=file,
            action=action,
            overrides=overrides,
            operation=operation,
        )
        bundle: dict = {"mode": "discussion-context", "layer": layer, "version": version}
        tnode = view.node(target_id)
        target: dict = {"id": target_id, "exists": tnode is not None}
        if tnode is not None:
            item = self._context_item_for_spec(tnode)
            if item is not None:
                target["file"] = item["file"]
                target["content"] = item["content"]
        bundle["target"] = target

        if layer == "prd":
            # 现状 = baseline∪版本视图中的全部 PRD chunk(修改方向在用户对话里)
            # target 自身不再重复出现在 related 里(讨论背景内容正确性收口)。
            related: list[dict] = []
            seen: set[str] = {target_id}
            for cid in sorted(view.nodes):
                if cid.startswith("[PRD]-") and cid != target_id:
                    self._append_context_item(related, seen, view.nodes[cid])
            bundle["related"] = related
            bundle["context_token"] = self._context_token(intent, bundle)
            return bundle

        if parent_id is not None:
            # 锚定式: the command names the anchor.
            result = self._assemble_anchored_bundle(view, bundle, parent_id)
            result["context_token"] = self._context_token(intent, result)
            return result

        if layer == "fsd" and tnode is not None:
            # 修改既有子 FSD(讨论目标本身已存在,而非在其下新建子块)时自动切换为
            # 锚定式:治理该子块的 parent split 才是真正的讨论中心,而不是笼统的
            # 上层 [PRD]- 改动摘要(讨论背景内容正确性收口)。
            governing = view.edges_to(target_id, "decomposes")
            if governing:
                result = self._assemble_anchored_bundle(view, bundle, governing[0].src)
                result["context_token"] = self._context_token(intent, result)
                return result

        # 发现式: anchors = this version's upper-layer changed chunks.
        upper_prefix = "[PRD]-" if layer == "fsd" else "[FSD]-"
        idx = self.indexes.load_version_index(version)
        anchors: list[dict] = []
        aseen: set[str] = set()
        for entry in sorted(idx.chunks, key=lambda item: item.id):
            if not entry.id.startswith(upper_prefix) or entry.action not in ("add", "modify"):
                continue
            if entry.id in aseen:
                continue
            node = view.node(entry.id)
            if node is None:
                continue
            aseen.add(entry.id)
            item = self._context_item_for_spec(node)
            if item is not None:
                item["action"] = entry.action
                anchors.append(item)
        bundle["anchors"] = anchors
        related = []
        rseen: set[str] = set(aseen) | {target_id}
        for a in anchors:
            for edge in sorted(
                [*view.edges_from(a["id"]), *view.edges_to(a["id"])],
                key=lambda item: (
                    item.dst if item.src == a["id"] else item.src,
                    item.rel,
                    item.src,
                    item.dst,
                ),
            ):
                other = edge.dst if edge.src == a["id"] else edge.src
                if other in rseen:
                    continue
                node = view.node(other)
                if node is None:
                    continue
                rseen.add(other)
                item = self._context_item_for_spec(node)
                if item is not None:
                    item["via"] = edge.rel
                    item["anchor"] = a["id"]
                    related.append(item)
        bundle["related"] = related
        bundle["context_token"] = self._context_token(intent, bundle)
        return bundle

    def _assemble_anchored_bundle(
        self, view: Any, bundle: dict[str, Any], parent_id: str
    ) -> dict[str, Any]:
        """Populate the parent-centred discussion context shared by explicit
        and auto-discovered anchoring paths."""
        pnode = view.node(parent_id)
        if pnode is None:
            raise _validation_error(
                "MISSING_ENDPOINT", f"parent {parent_id} not found", parent_id
            )
        anchor_items: list[dict[str, Any]] = []
        self._append_context_item(anchor_items, set(), pnode)
        bundle["anchor"] = anchor_items[0] if anchor_items else {"id": parent_id}

        linked: list[dict[str, Any]] = []
        seen: set[str] = {parent_id}
        for edge in sorted(
            [*view.edges_from(parent_id), *view.edges_to(parent_id)],
            key=lambda item: (
                item.dst if item.src == parent_id else item.src,
                item.rel,
                item.src,
                item.dst,
            ),
        ):
            other = edge.dst if edge.src == parent_id else edge.src
            if other in seen:
                continue
            node = view.node(other)
            if node is None:
                continue
            seen.add(other)
            item = self._context_item_for_spec(node)
            if item is not None:
                item["rel"] = edge.rel
                item["direction"] = "out" if edge.src == parent_id else "in"
                linked.append(item)
        bundle["linked"] = linked

        upstream: list[dict[str, Any]] = []
        seen = {parent_id}
        if ":" in parent_id:
            root_node = view.node(_parent_chunk_id(parent_id))
            if root_node is not None:
                self._append_context_item(upstream, seen, root_node)
                self._walk_upstream_roots(view, root_node.chunk_id, upstream, seen)
        else:
            self._walk_upstream_roots(view, parent_id, upstream, seen)
        bundle["upstream"] = upstream
        return bundle

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
        parent_id: str | None,
        operation: str,
        context_token: str | None,
        skip_context: bool,
        index_chunk_ids: set[str] | None = None,
    ) -> DocumentCreateResult:
        file = _validated_index_path(file, kind) if file else f"{kind}/{root_chunk_id}"
        # gap-4 closure: every chunk in a new-model doc must carry the kind's
        # bracket prefix. A non-prefixed chunk would get type=prd/fsd/tdd (by
        # file location) yet escape the six-invariant sampling — the validator's
        # _is_new_model_spec keys on the prefix — so it could occupy a
        # target_file / graph node while dodging orphan/traceability/uniqueness.
        # Reject at the entry, before any write: zero-write, retryable.
        prefix = _NEW_MODEL_PREFIX_BY_KIND[kind]
        if not root_chunk_id.startswith(prefix):
            raise _validation_error(
                "CHUNK_ID_PREFIX_REQUIRED",
                f"{kind} root chunk id must start with '{prefix}', got: {root_chunk_id}",
                root_chunk_id,
            )
        parsed = parse_text(content, file=file)
        root = next((chunk for chunk in parsed.chunks if chunk.id == root_chunk_id), None)
        if root is None:
            raise _validation_error(
                "ROOT_CHUNK_REQUIRED",
                f"{kind.upper()} markdown must include root chunk {root_chunk_id}",
                root_chunk_id,
            )
        for chunk in parsed.chunks:
            if not chunk.id.startswith(prefix):
                raise _validation_error(
                    "CHUNK_ID_PREFIX_REQUIRED",
                    f"every {kind} chunk id must start with '{prefix}', got: {chunk.id}",
                    chunk.id,
                )
            # relation birth boundary closure: relations are born only via the
            # four canonical entry points — reject any markdown body residue
            # of @ref/@extract annotations, or (outside fsd, where a legal
            # depends_on/derives yaml fence is stripped before it reaches
            # this content, see create_fsd's clean_content) a depends_on/
            # derives declaration block. Zero-write, retryable.
            relation_violations = scan_content_relations(chunk.content, kind)
            if relation_violations:
                first = relation_violations[0]
                raise _validation_error(first.code, first.message, chunk.id)

        # P7: every layer requires an already-created version — no auto-create,
        # no ghost. `version create` is the sole entry (prd create no longer
        # bootstraps a version). Missing → VERSION_NOT_FOUND.
        if not self.versions.version_meta_path(version).exists():
            raise _validation_error(
                "VERSION_NOT_FOUND",
                f"version {version} does not exist — run `version create` first",
                root_chunk_id,
            )
        usage = self._validate_context(
            version=version,
            layer=kind,
            target_id=root_chunk_id,
            parent_id=parent_id,
            file=file,
            action=action,
            overrides=overrides,
            operation=operation,
            context_token=context_token,
            skip_context=skip_context,
        )
        path = self.versions.write_version_file(version, file, content)
        final_parsed = parse_file(path, self.versions.versions_dir / version)
        chunk_ids: list[str] = []
        for chunk in final_parsed.chunks:
            if index_chunk_ids is not None and chunk.id not in index_chunk_ids:
                continue
            self.versions.add_chunk(
                version,
                chunk=chunk,
                action=action,  # type: ignore[arg-type]
                overrides=overrides if chunk.id == root_chunk_id else None,
                discussion_usage=usage,
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


def _split_derives(chunk_content: str) -> list[str] | None:
    """Declared PRD-requirement derives from a split chunk's yaml fence block.

    Same semantics as _split_depends_on but for the ``derives:`` key.
    """
    import yaml

    for block in _YAML_FENCE_RE.findall(chunk_content):
        try:
            loaded = yaml.safe_load(block)
        except Exception:
            continue
        if isinstance(loaded, dict) and "derives" in loaded:
            value = loaded["derives"]
            if isinstance(value, list):
                return [str(item) for item in value]
            return []
    return None


def _strip_depends_on_blocks(content: str) -> str:
    """Remove transient ``depends_on:``/``derives:`` yaml fence blocks from FSD markdown.

    The declaration is an input instruction consumed to build specgraph edges,
    never persisted doc content (a chunk↔chunk relation belongs only in
    specgraph). Non-depends_on/derives yaml fences are left untouched.
    """
    import yaml

    def _drop(match: "re.Match[str]") -> str:
        try:
            loaded = yaml.safe_load(match.group("body"))
        except Exception:
            return match.group(0)
        if isinstance(loaded, dict) and ("depends_on" in loaded or "derives" in loaded):
            return ""
        return match.group(0)

    return _YAML_FENCE_FULL_RE.sub(_drop, content)


def _parent_chunk_id(chunk_id: str) -> str:
    return chunk_id.split(":", 1)[0]


def _file_stem(file: str) -> str:
    return file.rsplit("/", 1)[-1]


_NEW_MODEL_PREFIX_BY_KIND = {"prd": "[PRD]-", "fsd": "[FSD]-", "tdd": "[TDD]-"}


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
