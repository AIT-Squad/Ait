"""Block-level Markdown parser.

Implements project-docs/docs/prd/block-system.md:
    - Block boundaries from `<!-- @id:xxx -->` annotations (not heading levels)
    - File header = content before first @id
    - `<!-- @ref:file#id rel:type -->` annotations attributed to enclosing block
    - Code-fence content is masked to avoid false @id/@ref matches

Pure parsing — no I/O beyond `parse_file`. Index writing happens elsewhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .io_utils import strip_md_ext, to_posix_rel

ID_PATTERN = re.compile(r"^<!--\s*@id:([a-z0-9-]+)\s*-->\s*$")
REF_PATTERN = re.compile(
    r"<!--\s*@ref:([\w\-/.]+)#([a-z0-9-]+)\s+rel:([a-z\-]+)\s*-->"
)
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
CODE_FENCE_PATTERN = re.compile(r"^\s*(```+|~~~+)")


@dataclass(frozen=True)
class Block:
    id: str
    heading: str
    level: int
    content: str
    line_start: int
    line_end: int
    file: str


@dataclass(frozen=True)
class Ref:
    source_block_id: str
    target_file: str
    target_block_id: str
    rel: str


@dataclass(frozen=True)
class ParsedFile:
    file: str
    file_header: str
    blocks: list[Block] = field(default_factory=list)
    refs: list[Ref] = field(default_factory=list)


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _mask_code_fences(lines: list[str]) -> list[bool]:
    """Return a boolean mask marking lines inside code fences (True = inside)."""
    inside = False
    fence: str | None = None
    mask: list[bool] = []
    for line in lines:
        m = CODE_FENCE_PATTERN.match(line)
        if m:
            opener = m.group(1)[:3]  # ``` or ~~~
            if not inside:
                inside = True
                fence = opener
                mask.append(True)
                continue
            if fence is not None and line.lstrip().startswith(fence):
                mask.append(True)
                inside = False
                fence = None
                continue
        mask.append(inside)
    return mask


def _find_heading(lines: list[str], start_idx: int, masked: list[bool]) -> tuple[str, int]:
    """Find the first heading line at or after `start_idx`; skip masked (code) lines."""
    for i in range(start_idx, len(lines)):
        if masked[i]:
            continue
        m = HEADING_PATTERN.match(lines[i])
        if m:
            return m.group(2).strip(), len(m.group(1))
    return "", 0


def parse_text(text: str, file: str) -> ParsedFile:
    """Parse markdown text into blocks + refs.

    `file` is the index-form path (relative to docs/ root, no `.md`).
    """
    text = _normalize(text)
    lines = text.split("\n")
    masked = _mask_code_fences(lines)

    id_positions: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if masked[i]:
            continue
        m = ID_PATTERN.match(line)
        if m:
            id_positions.append((i, m.group(1)))

    blocks: list[Block] = []
    if not id_positions:
        # Whole file is header.
        return ParsedFile(file=file, file_header=text, blocks=[], refs=[])

    file_header = "\n".join(lines[: id_positions[0][0]]).rstrip()

    for idx, (line_idx, block_id) in enumerate(id_positions):
        end_idx = (
            id_positions[idx + 1][0] - 1
            if idx + 1 < len(id_positions)
            else len(lines) - 1
        )
        # Trim trailing blank lines from block body (but keep at least the annotation line).
        while end_idx > line_idx and lines[end_idx].strip() == "":
            end_idx -= 1

        content = "\n".join(lines[line_idx : end_idx + 1])
        heading, level = _find_heading(lines, line_idx + 1, masked)

        blocks.append(
            Block(
                id=block_id,
                heading=heading,
                level=level,
                content=content,
                line_start=line_idx + 1,
                line_end=end_idx + 1,
                file=file,
            )
        )

    refs = _extract_refs(lines, masked, blocks)
    return ParsedFile(file=file, file_header=file_header, blocks=blocks, refs=refs)


def _extract_refs(
    lines: list[str], masked: list[bool], blocks: list[Block]
) -> list[Ref]:
    refs: list[Ref] = []
    if not blocks:
        return refs

    # Map each line to its enclosing block_id (1-indexed in Block.line_start/end).
    line_owner: list[str | None] = [None] * len(lines)
    for block in blocks:
        for ln in range(block.line_start - 1, block.line_end):
            if 0 <= ln < len(lines):
                line_owner[ln] = block.id

    for i, line in enumerate(lines):
        if masked[i]:
            continue
        for m in REF_PATTERN.finditer(line):
            owner = line_owner[i]
            if owner is None:
                continue  # @ref in file header — ignored per spec
            refs.append(
                Ref(
                    source_block_id=owner,
                    target_file=m.group(1),
                    target_block_id=m.group(2),
                    rel=m.group(3),
                )
            )
    return refs


def parse_file(path: Path, base_dir: Path) -> ParsedFile:
    """Parse a markdown file. `base_dir` is e.g. `docs/` or `versions/v1.1/`."""
    rel = to_posix_rel(base_dir, path)
    file = strip_md_ext(rel)
    text = path.read_text(encoding="utf-8")
    return parse_text(text, file)
