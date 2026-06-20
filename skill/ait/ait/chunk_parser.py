"""Chunk-level Markdown parser.

Implements project-docs/docs/prd/block-system.md:
    - Chunk boundaries from `<!-- @id:xxx -->` annotations (not heading levels)
    - File header = content before first @id
    - `<!-- @ref:file#id rel:type -->` annotations attributed to enclosing chunk
    - Code-fence content is masked to avoid false @id/@ref matches

Pure parsing — no I/O beyond `parse_file`. Index writing happens elsewhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .io_utils import strip_md_ext, to_posix_rel

LEGACY_CHUNK_ID = r"[a-z0-9][a-z0-9-]*"
NEW_MODEL_CHUNK_ID = r"\[(?:PRD|FSD|TDD)\]-[a-z0-9_]+(?:-[a-z0-9_]+)*(?::[a-z0-9_]+)?"
CHUNK_ID_PATTERN = rf"(?:{LEGACY_CHUNK_ID}|{NEW_MODEL_CHUNK_ID})"

ID_PATTERN = re.compile(rf"^<!--\s*@id:({CHUNK_ID_PATTERN})\s*-->\s*$")
REF_PATTERN = re.compile(
    rf"<!--\s*@ref:([^#\s]+)#({CHUNK_ID_PATTERN})\s+rel:([a-z][a-z0-9_-]*)\s*-->"
)
# @extract:dynamic/{type}#{chunk}  ...  @extract-end
# Marks a fragment inside an impl chunk that should be extracted into dynamic
# global (DDL/schema/api) at version-confirm time.
EXTRACT_OPEN_PATTERN = re.compile(
    r"^<!--\s*@extract:([\w\-]+)/([\w\-]+)#([a-z0-9-]+)\s*-->\s*$"
)
EXTRACT_END_PATTERN = re.compile(r"^<!--\s*@extract-end\s*-->\s*$")
NO_IMPL_PATTERN = re.compile(r"^<!--\s*@prd-no-impl\s*-->\s*$")
SUMMARY_PATTERN = re.compile(r"^<!--\s*@summary:\s*(.+?)\s*-->\s*$")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
CODE_FENCE_PATTERN = re.compile(r"^\s*(```+|~~~+)")


@dataclass(frozen=True)
class Chunk:
    id: str
    heading: str
    level: int
    content: str
    line_start: int
    line_end: int
    file: str
    no_impl: bool = False
    summary: str | None = None

@dataclass(frozen=True)
class Ref:
    source_chunk_id: str
    target_file: str
    target_chunk_id: str
    rel: str

@dataclass(frozen=True)
class ExtractBlock:
    source_chunk_id: str   # the @id chunk the @extract lives in ("" if outside any)
    target_type: str       # e.g. "ddl" / "schema" / "api"  (the part after dynamic/)
    target_category: str   # e.g. "dynamic"  (the part before /)
    target_chunk: str      # chunk id to write into dynamic global
    content: str           # raw text between @extract and @extract-end (markers excluded)
    line_start: int        # 1-indexed, the @extract opener line
    line_end: int          # 1-indexed, the @extract-end line

@dataclass(frozen=True)
class ParsedFile:
    file: str
    file_header: str
    chunks: list[Chunk] = field(default_factory=list)
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
    """Parse markdown text into chunks + refs.

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

    chunks: list[Chunk] = []
    if not id_positions:
        # Whole file is header.
        return ParsedFile(file=file, file_header=text, chunks=[], refs=[])

    file_header = "\n".join(lines[: id_positions[0][0]]).rstrip()

    for idx, (line_idx, chunk_id) in enumerate(id_positions):
        end_idx = (
            id_positions[idx + 1][0] - 1
            if idx + 1 < len(id_positions)
            else len(lines) - 1
        )
        # Trim trailing blank lines from chunk body (but keep at least the annotation line).
        while end_idx > line_idx and lines[end_idx].strip() == "":
            end_idx -= 1

        content_lines = lines[line_idx : end_idx + 1]
        summary: str | None = None
        for offset, line in enumerate(content_lines):
            if masked[line_idx + offset]:
                continue
            if match := SUMMARY_PATTERN.match(line):
                summary = match.group(1).strip()
        no_impl = any(
            not masked[line_idx + offset] and NO_IMPL_PATTERN.match(line)
            for offset, line in enumerate(content_lines)
        )
        stripped_lines: list[str] = []
        skip_next_blank = False
        for offset, line in enumerate(content_lines):
            is_marker = (
                not masked[line_idx + offset]
                and (NO_IMPL_PATTERN.match(line) or SUMMARY_PATTERN.match(line))
            )
            if is_marker:
                skip_next_blank = bool(stripped_lines and stripped_lines[-1].strip() == "")
                continue
            if skip_next_blank and line.strip() == "":
                skip_next_blank = False
                continue
            skip_next_blank = False
            stripped_lines.append(line)
        content_lines = stripped_lines
        content = "\n".join(content_lines)
        heading, level = _find_heading(lines, line_idx + 1, masked)

        chunks.append(
            Chunk(
                id=chunk_id,
                heading=heading,
                level=level,
                content=content,
                line_start=line_idx + 1,
                line_end=end_idx + 1,
                file=file,
                no_impl=no_impl,
                summary=summary,
            )
        )

    refs = _extract_refs(lines, masked, chunks)
    return ParsedFile(file=file, file_header=file_header, chunks=chunks, refs=refs)

def _extract_refs(
    lines: list[str], masked: list[bool], chunks: list[Chunk]
) -> list[Ref]:
    refs: list[Ref] = []
    if not chunks:
        return refs

    # Map each line to its enclosing chunk_id (1-indexed in Chunk.line_start/end).
    line_owner: list[str | None] = [None] * len(lines)
    for chunk in chunks:
        for ln in range(chunk.line_start - 1, chunk.line_end):
            if 0 <= ln < len(lines):
                line_owner[ln] = chunk.id

    for i, line in enumerate(lines):
        if masked[i]:
            continue
        for m in REF_PATTERN.finditer(line):
            owner = line_owner[i]
            if owner is None:
                continue  # @ref in file header — ignored per spec
            refs.append(
                Ref(
                    source_chunk_id=owner,
                    target_file=m.group(1),
                    target_chunk_id=m.group(2),
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


class ExtractError(ValueError):
    """Raised when an @extract block is malformed (unclosed / nested)."""


def parse_extract_blocks(text: str, *, chunks: list[Chunk] | None = None) -> list[ExtractBlock]:
    """Parse `@extract:cat/type#chunk ... @extract-end` blocks from markdown.

    The opener/closer markers are HTML comments living OUTSIDE code fences;
    the body between them (which may itself contain a fenced code block) is
    captured verbatim with markers excluded.

    Pass `chunks` (from parse_text) to attribute each block to its enclosing
    @id chunk; otherwise source_chunk_id is "".

    Raises ExtractError on an unclosed opener or a nested opener.
    """
    text = _normalize(text)
    lines = text.split("\n")
    masked = _mask_code_fences(lines)

    # Map line index -> enclosing chunk id (1-indexed bounds in Chunk).
    owner: list[str] = [""] * len(lines)
    for chunk in chunks or []:
        for ln in range(chunk.line_start - 1, chunk.line_end):
            if 0 <= ln < len(lines):
                owner[ln] = chunk.id

    blocks: list[ExtractBlock] = []
    open_at: int | None = None
    open_meta: tuple[str, str, str] | None = None  # (category, type, chunk)

    for i, line in enumerate(lines):
        if masked[i]:
            continue  # markers never live inside code fences
        mo = EXTRACT_OPEN_PATTERN.match(line)
        if mo:
            if open_at is not None:
                raise ExtractError(
                    f"nested @extract at line {i + 1} (previous opened at line {open_at + 1})"
                )
            open_at = i
            open_meta = (mo.group(1), mo.group(2), mo.group(3))
            continue
        if EXTRACT_END_PATTERN.match(line):
            if open_at is None:
                raise ExtractError(f"@extract-end without opener at line {i + 1}")
            assert open_meta is not None
            body = "\n".join(lines[open_at + 1 : i]).strip("\n")
            blocks.append(
                ExtractBlock(
                    source_chunk_id=owner[open_at],
                    target_category=open_meta[0],
                    target_type=open_meta[1],
                    target_chunk=open_meta[2],
                    content=body,
                    line_start=open_at + 1,
                    line_end=i + 1,
                )
            )
            open_at = None
            open_meta = None

    if open_at is not None:
        raise ExtractError(f"unclosed @extract opened at line {open_at + 1}")
    return blocks
