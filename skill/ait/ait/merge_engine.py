"""Pure chunk-level merge engine.

Per project-docs/docs/impl/merge-engine.md. No I/O — only operates on in-memory
ParsedFile + a list of VersionChunkOp. Calling code (`version_manager.merge`)
is responsible for reading baseline files, conflict detection, and writing the
result back to disk.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256

from .chunk_parser import Chunk, ParsedFile, parse_text
from .schemas import Action, ReconciliationOperation, ReconciliationPlan


@dataclass(frozen=True)
class VersionChunkOp:
    chunk_id: str
    action: Action
    overrides: str | None = None
    insert_after: str | None = None
    new_chunk: Chunk | None = None
    base_hash: str | None = None

@dataclass(frozen=True)
class MergedFile:
    file: str
    file_header: str
    chunks: list[Chunk]
    new_content: str


def reconciliation_input_fingerprint(
    baseline_files: Mapping[str, ParsedFile],
    operations: Iterable[ReconciliationOperation],
    conflict_policy: str,
    *,
    specgraph_inputs: Mapping[str, str] | None = None,
) -> str:
    """Fingerprint explicit reconciliation and graph inputs with stable JSON."""
    payload = {
        "baseline": [
            {
                "file": file,
                "header": parsed.file_header,
                "chunks": [{"id": chunk.id, "content": chunk.content} for chunk in parsed.chunks],
            }
            for file, parsed in sorted(baseline_files.items())
        ],
        "operations": [operation.model_dump(mode="json") for operation in operations],
        "conflict_policy": conflict_policy,
        "specgraph": dict(sorted((specgraph_inputs or {}).items())),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(encoded.encode("utf-8")).hexdigest()


def plan_reconciliation(
    baseline_files: Mapping[str, ParsedFile],
    operations: Iterable[ReconciliationOperation],
    *,
    conflict_policy: str,
    input_fingerprint: str | None = None,
) -> ReconciliationPlan:
    """Normalize explicit operations once for both confirm and merge.

    A modify targeting a chunk absent from the baseline is a semantic add. The
    normalized action is persisted so execution never needs to reinterpret it.
    """
    raw_operations = list(operations)
    baseline_ids = {
        chunk.id
        for parsed in baseline_files.values()
        for chunk in parsed.chunks
    }
    normalized: list[ReconciliationOperation] = []
    for operation in raw_operations:
        target = operation.target_id or operation.chunk_id
        if operation.action == "modify" and target not in baseline_ids:
            normalized.append(
                operation.model_copy(update={"action": "add", "target_id": None})
            )
        else:
            normalized.append(operation)
    return ReconciliationPlan(
        operations=normalized,
        input_fingerprint=input_fingerprint
        or reconciliation_input_fingerprint(baseline_files, raw_operations, conflict_policy),
        conflict_policy=conflict_policy,  # type: ignore[arg-type]
    )


def execute_plan(
    plan: ReconciliationPlan,
    baseline_files: Mapping[str, ParsedFile],
) -> list[MergedFile]:
    """Execute an already-confirmed plan without reclassifying any action."""
    by_file: dict[str, list[VersionChunkOp]] = {}
    for operation in plan.operations:
        new_chunk: Chunk | None = None
        if operation.new_content is not None:
            parsed = parse_text(operation.new_content, operation.file)
            new_chunk = next((chunk for chunk in parsed.chunks if chunk.id == operation.chunk_id), None)
            if new_chunk is None:
                raise ValueError(
                    f"reconciliation operation content does not contain {operation.chunk_id}"
                )
        by_file.setdefault(operation.file, []).append(
            VersionChunkOp(
                chunk_id=operation.chunk_id,
                action=operation.action,
                overrides=operation.target_id,
                insert_after=operation.insert_after,
                new_chunk=new_chunk,
                base_hash=operation.base_hash,
            )
        )

    merged: list[MergedFile] = []
    for file, operations in by_file.items():
        baseline = baseline_files.get(file)
        if baseline is None:
            merged.append(merge_new_file(file, operations))
        else:
            merged.append(merge_file(baseline, operations))
    return merged


def _serialize(file_header: str, chunks: Iterable[Chunk]) -> str:
    parts: list[str] = []
    header = file_header.rstrip()
    if header:
        parts.append(header)
    for chunk in chunks:
        parts.append(chunk.content.strip())
    return "\n\n".join(parts) + "\n"

def serialize(file_header: str, chunks: Iterable[Chunk]) -> str:
    """Public alias of the serializer (useful for tests)."""
    return _serialize(file_header, chunks)


def merge_file(base: ParsedFile, ops: list[VersionChunkOp]) -> MergedFile:
    """Apply add/modify/delete operations to a baseline file."""
    if not base.chunks and any(op.action in ("modify", "delete") for op in ops):
        raise ValueError(
            "merge_file: baseline has no chunks but modify/delete ops were provided; "
            "use merge_new_file for brand-new files"
        )

    modify_map: dict[str, VersionChunkOp] = {}
    delete_set: set[str] = set()
    add_after_map: dict[str, list[VersionChunkOp]] = {}
    add_tail: list[VersionChunkOp] = []
    orphan_adds: list[VersionChunkOp] = []  # insert_after refers to a deleted chunk

    base_ids = {c.id for c in base.chunks}

    # First pass: classify ops. Action is reconciled against actual baseline
    # existence so a chunk is never silently dropped: a `modify` whose target is
    # absent from the baseline is a new chunk and is treated as an `add`.
    for op in ops:
        if op.action == "modify":
            target = op.overrides or op.chunk_id
            if target in base_ids:
                modify_map[target] = op
            else:
                # Not in baseline → effectively new; append rather than drop.
                add_tail.append(op)
        elif op.action == "delete":
            if op.overrides is not None:
                delete_set.add(op.overrides)
        elif op.action == "add":
            if op.insert_after is None:
                add_tail.append(op)
            elif op.insert_after in base_ids:
                add_after_map.setdefault(op.insert_after, []).append(op)
            else:
                orphan_adds.append(op)

    # Detect orphans: insert_after pointed at a base chunk now being deleted.
    pending_orphans: list[VersionChunkOp] = []
    for anchor, items in list(add_after_map.items()):
        if anchor in delete_set:
            pending_orphans.extend(items)
            del add_after_map[anchor]
    orphan_adds.extend(pending_orphans)

    # Second pass: rebuild chunk list.
    result: list[Chunk] = []
    last_kept_chunk: Chunk | None = None
    for chunk in base.chunks:
        if chunk.id in delete_set:
            # If we have orphan adds waiting on this anchor, drop them after the
            # last kept ancestor.
            if last_kept_chunk is not None:
                for orphan_op in [
                    o for o in orphan_adds if o.insert_after == chunk.id
                ]:
                    if orphan_op.new_chunk is not None:
                        result.append(orphan_op.new_chunk)
                        orphan_adds.remove(orphan_op)
            continue
        if chunk.id in modify_map:
            new_chunk = modify_map[chunk.id].new_chunk
            if new_chunk is None:
                raise ValueError(
                    f"modify op for {chunk.id} has new_chunk=None"
                )
            result.append(new_chunk)
        else:
            result.append(chunk)
        last_kept_chunk = result[-1]

        for op in add_after_map.get(chunk.id, []):
            if op.new_chunk is not None:
                result.append(op.new_chunk)
        # orphan adds anchored on a deleted chunk earlier — attach after the next survivor
        unattached = [
            o for o in orphan_adds if o.insert_after not in base_ids
        ]
        for op in unattached:
            if op.new_chunk is not None and op not in result:
                result.append(op.new_chunk)
                orphan_adds.remove(op)

    # Tail appends.
    for op in add_tail:
        if op.new_chunk is not None:
            result.append(op.new_chunk)

    # Any remaining orphans land at the very top (after header).
    for op in list(orphan_adds):
        if op.new_chunk is not None:
            result.insert(0, op.new_chunk)

    new_content = _serialize(base.file_header, result)
    return MergedFile(
        file=base.file,
        file_header=base.file_header,
        chunks=result,
        new_content=new_content,
    )

def merge_new_file(file: str, ops: list[VersionChunkOp]) -> MergedFile:
    """Build a brand-new file from add ops only (e.g. a new PRD file in the version)."""
    non_add = [op for op in ops if op.action != "add"]
    if non_add:
        raise ValueError("merge_new_file only accepts action=add ops")

    chunks: list[Chunk] = []
    for op in ops:
        if op.new_chunk is None:
            continue
        chunks.append(op.new_chunk)
    return MergedFile(
        file=file,
        file_header="",
        chunks=chunks,
        new_content=_serialize("", chunks),
    )
