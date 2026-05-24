"""Pure block-level merge engine.

Per project-docs/docs/impl/merge-engine.md. No I/O — only operates on in-memory
ParsedFile + a list of VersionBlockOp. Calling code (`version_manager.merge`)
is responsible for reading baseline files, conflict detection, and writing the
result back to disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .block_parser import Block, ParsedFile
from .schemas import Action


@dataclass(frozen=True)
class VersionBlockOp:
    block_id: str
    action: Action
    overrides: str | None = None
    insert_after: str | None = None
    new_block: Block | None = None
    base_hash: str | None = None


@dataclass(frozen=True)
class MergedFile:
    file: str
    file_header: str
    blocks: list[Block]
    new_content: str


def _serialize(file_header: str, blocks: Iterable[Block]) -> str:
    parts: list[str] = []
    header = file_header.rstrip()
    if header:
        parts.append(header)
    for block in blocks:
        parts.append(block.content.strip())
    return "\n\n".join(parts) + "\n"


def serialize(file_header: str, blocks: Iterable[Block]) -> str:
    """Public alias of the serializer (useful for tests)."""
    return _serialize(file_header, blocks)


def merge_file(base: ParsedFile, ops: list[VersionBlockOp]) -> MergedFile:
    """Apply add/modify/delete operations to a baseline file."""
    if not base.blocks and any(op.action in ("modify", "delete") for op in ops):
        raise ValueError(
            "merge_file: baseline has no blocks but modify/delete ops were provided; "
            "use merge_new_file for brand-new files"
        )

    modify_map: dict[str, VersionBlockOp] = {}
    delete_set: set[str] = set()
    add_after_map: dict[str, list[VersionBlockOp]] = {}
    add_tail: list[VersionBlockOp] = []
    orphan_adds: list[VersionBlockOp] = []  # insert_after refers to a deleted block

    base_ids = {b.id for b in base.blocks}

    # First pass: classify ops.
    for op in ops:
        if op.action == "modify":
            if op.overrides is None:
                continue
            modify_map[op.overrides] = op
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

    # Detect orphans: insert_after pointed at a base block now being deleted.
    pending_orphans: list[VersionBlockOp] = []
    for anchor, items in list(add_after_map.items()):
        if anchor in delete_set:
            pending_orphans.extend(items)
            del add_after_map[anchor]
    orphan_adds.extend(pending_orphans)

    # Second pass: rebuild block list.
    result: list[Block] = []
    last_kept_block: Block | None = None
    for block in base.blocks:
        if block.id in delete_set:
            # If we have orphan adds waiting on this anchor, drop them after the
            # last kept ancestor.
            if last_kept_block is not None:
                for orphan_op in [
                    o for o in orphan_adds if o.insert_after == block.id
                ]:
                    if orphan_op.new_block is not None:
                        result.append(orphan_op.new_block)
                        orphan_adds.remove(orphan_op)
            continue
        if block.id in modify_map:
            new_block = modify_map[block.id].new_block
            if new_block is None:
                raise ValueError(
                    f"modify op for {block.id} has new_block=None"
                )
            result.append(new_block)
        else:
            result.append(block)
        last_kept_block = result[-1]

        for op in add_after_map.get(block.id, []):
            if op.new_block is not None:
                result.append(op.new_block)
        # orphan adds anchored on a deleted block earlier — attach after the next survivor
        unattached = [
            o for o in orphan_adds if o.insert_after not in base_ids
        ]
        for op in unattached:
            if op.new_block is not None and op not in result:
                result.append(op.new_block)
                orphan_adds.remove(op)

    # Tail appends.
    for op in add_tail:
        if op.new_block is not None:
            result.append(op.new_block)

    # Any remaining orphans land at the very top (after header).
    for op in list(orphan_adds):
        if op.new_block is not None:
            result.insert(0, op.new_block)

    new_content = _serialize(base.file_header, result)
    return MergedFile(
        file=base.file,
        file_header=base.file_header,
        blocks=result,
        new_content=new_content,
    )


def merge_new_file(file: str, ops: list[VersionBlockOp]) -> MergedFile:
    """Build a brand-new file from add ops only (e.g. a new PRD file in the version)."""
    non_add = [op for op in ops if op.action != "add"]
    if non_add:
        raise ValueError("merge_new_file only accepts action=add ops")

    blocks: list[Block] = []
    for op in ops:
        if op.new_block is None:
            continue
        blocks.append(op.new_block)
    return MergedFile(
        file=file,
        file_header="",
        blocks=blocks,
        new_content=_serialize("", blocks),
    )
