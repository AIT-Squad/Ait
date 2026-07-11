"""Managers for v2 PRD/FSD/TDD-side document commands."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .chunk_parser import Chunk, parse_file, parse_text
from .index_manager import IndexManager
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
        return self._create_document(
            version,
            root_chunk_id,
            content,
            kind="fsd",
            file=file,
            action=action,
            overrides=overrides,
        )

    def create_tdd(
        self,
        version: str,
        root_chunk_id: str,
        content: str,
        *,
        file: str | None = None,
        action: str = "add",
        overrides: str | None = None,
    ) -> DocumentCreateResult:
        if not _target_file(content):
            raise _validation_error("TDD_TARGET_FILE_REQUIRED", "TDD markdown must include target_file")
        return self._create_document(
            version,
            root_chunk_id,
            content,
            kind="tdd",
            file=file,
            action=action,
            overrides=overrides,
        )

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
        return self._create_document(
            version,
            root_chunk_id,
            content,
            kind="prd",
            file=file,
            action=action,
            overrides=overrides,
        )

    def add_edge(self, version: str, src: str, dst: str, rel: str) -> EdgeCreateResult:
        if rel not in NEW_MODEL_RELS:
            raise _validation_error(
                "INVALID_NEW_MODEL_REL",
                "new-model relation must be one of: decomposes, details, depends_on",
                src,
            )
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
        file = file or f"{kind}/{root_chunk_id}"
        parsed = parse_text(content, file=file)
        root = next((chunk for chunk in parsed.chunks if chunk.id == root_chunk_id), None)
        if root is None:
            raise _validation_error(
                "ROOT_CHUNK_REQUIRED",
                f"{kind.upper()} markdown must include root chunk {root_chunk_id}",
                root_chunk_id,
            )

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


def _target_file(text: str) -> str | None:
    match = TARGET_FILE_RE.search(text)
    return match.group(1).strip() if match else None


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
