"""I/O utilities: atomic writes and project-root path guards.

Writes go to a `.tmp` sibling then `os.replace`, which is atomic on POSIX and
on Windows since the os.replace contract guarantees overwrite-on-rename.
"""

from __future__ import annotations

import os
from pathlib import Path


class PathOutsideProjectError(ValueError):
    """Raised when a write target escapes the project root."""


def ensure_within(project_root: Path, target: Path) -> Path:
    """Resolve `target` and assert it lives under `project_root`.

    Returns the resolved absolute path. Raises PathOutsideProjectError otherwise.
    """
    root = project_root.resolve()
    resolved = (root / target).resolve() if not target.is_absolute() else target.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PathOutsideProjectError(
            f"Path {resolved} escapes project root {root}"
        ) from exc
    return resolved


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write text atomically via tmp+rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding=encoding, newline="\n") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write bytes atomically via tmp+rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise


def to_posix_rel(root: Path, path: Path) -> str:
    """Return `path` relative to `root` using POSIX separators."""
    return path.resolve().relative_to(root.resolve()).as_posix()


def strip_md_ext(rel_path: str) -> str:
    """Strip a trailing `.md` extension if present (used for index `file` field)."""
    return rel_path[:-3] if rel_path.endswith(".md") else rel_path
