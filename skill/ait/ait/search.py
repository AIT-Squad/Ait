"""Search committed AIT chunks by keyword or regular expression."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .chunk_parser import parse_file
from .index_manager import IndexManager


@dataclass
class SearchHit:
    chunk_id: str
    file: str
    heading: str
    version: str | None
    source: str
    snippet: str


def search_chunks(
    project_root: Path,
    query: str,
    *,
    scope: str = "all",
    regexp: bool = False,
) -> list[SearchHit]:
    indexes = IndexManager(project_root)
    hits: list[SearchHit] = []

    if scope in {"all", "prd", "impl"}:
        for entry in indexes.load_baseline().chunks:
            if not _scope_matches(entry.file, scope):
                continue
            path = project_root / "docs" / f"{entry.file}.md"
            hit = _match_entry(path, project_root / "docs", entry.id, entry.heading, query, regexp, None, "baseline")
            if hit:
                hits.append(hit)

    for version in indexes.list_versions():
        idx = indexes.load_version_index(version)
        for entry in idx.chunks:
            if entry.state != "committed" or not entry.file:
                continue
            if not _scope_matches(entry.file, scope):
                continue
            path = project_root / "versions" / version / f"{entry.file}.md"
            hit = _match_entry(
                path,
                project_root / "versions" / version,
                entry.id,
                entry.heading or "",
                query,
                regexp,
                version,
                "version",
            )
            if hit:
                hits.append(hit)

    return hits


def _scope_matches(file: str, scope: str) -> bool:
    if scope == "all":
        return file.startswith("prd/") or file.startswith("impl/")
    return file.startswith(f"{scope}/")


def _match_entry(
    path: Path,
    base_dir: Path,
    chunk_id: str,
    heading: str,
    query: str,
    regexp: bool,
    version: str | None,
    source: str,
) -> SearchHit | None:
    if not path.exists():
        return None
    parsed = parse_file(path, base_dir)
    for chunk in parsed.chunks:
        if chunk.id != chunk_id:
            continue
        snippet = match_chunk(chunk.content, query, regexp)
        if snippet is None:
            return None
        return SearchHit(
            chunk_id=chunk.id,
            file=chunk.file,
            heading=heading or chunk.heading,
            version=version,
            source=source,
            snippet=snippet,
        )
    return None


def match_chunk(content: str, query: str, regexp: bool = False) -> str | None:
    lines = content.splitlines()
    if regexp:
        pattern = re.compile(query, re.IGNORECASE)
        for i, line in enumerate(lines):
            if pattern.search(line):
                return extract_snippet(lines, i)
        return None
    needle = query.lower()
    for i, line in enumerate(lines):
        if needle in line.lower():
            return extract_snippet(lines, i)
    return None


def extract_snippet(lines: list[str], match_index: int, radius: int = 1) -> str:
    start = max(0, match_index - radius)
    end = min(len(lines), match_index + radius + 1)
    return "\n".join(lines[start:end])