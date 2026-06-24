"""Validation for the PRD/FSD/TDD chunk graph model."""

from __future__ import annotations

from dataclasses import dataclass

from .specgraph import Edge, Spec, SpecGraph

ALLOWED_RELS = {"decomposes", "details", "depends_on"}
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
                    "new-model graph relations must be one of: decomposes, details, depends_on",
                    src,
                )
            )
            continue

        if edge.rel == "decomposes":
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


def validate_target_file_uniqueness(
    entries: list[tuple[str, str | None, str | None]]
) -> list[NewModelViolation]:
    """Reject the case where two distinct TDD root chunks declare the same target_file.

    ``entries`` is a list of ``(chunk_id, file, target_file)`` tuples, one per TDD
    root chunk. TDDs without a ``target_file`` are ignored here (that is the
    separate ``TDD_TARGET_FILE_REQUIRED`` concern). This is the hard guarantee
    behind "different people do not edit the same file".
    """
    by_target: dict[str, list[tuple[str, str | None]]] = {}
    for chunk_id, file, target_file in entries:
        if not target_file:
            continue
        by_target.setdefault(target_file, []).append((chunk_id, file))

    violations: list[NewModelViolation] = []
    for target_file, owners in sorted(by_target.items()):
        if len(owners) > 1:
            owner_ids = sorted(chunk_id for chunk_id, _ in owners)
            violations.append(
                NewModelViolation(
                    code="DUPLICATE_TARGET_FILE",
                    message=(
                        f"target_file '{target_file}' is declared by multiple TDDs: "
                        + ", ".join(owner_ids)
                    ),
                    chunk_id=owner_ids[0],
                    file=sorted(owners)[0][1],
                )
            )
    return violations


def _validate_decomposes(edge: Edge, src: Spec, dst: Spec) -> list[NewModelViolation]:
    if src.type == "prd" and dst.type == "fsd":
        if _is_root_chunk(src) and _is_root_chunk(dst):
            return []
        return [
            _violation(
                edge,
                "INVALID_PRD_DECOMPOSES",
                "PRD decomposes must connect the PRD root chunk to the root FSD root chunk",
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
