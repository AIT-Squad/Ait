"""Hash utilities for chunk content fingerprinting.

Per project-docs/docs/prd/index-system.md, chunk hashes are the first 8 hex
chars of SHA-256 over normalized content (LF newlines, trimmed).
"""

from __future__ import annotations

import hashlib


def normalize(text: str) -> str:
    """Normalize text for hashing: CRLF→LF, strip leading/trailing whitespace."""
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def chunk_hash(content: str) -> str:
    """Compute the 8-char SHA-256 prefix for a chunk's content."""
    digest = hashlib.sha256(normalize(content).encode("utf-8")).hexdigest()
    return digest[:8]

def file_hash(path_content: str) -> str:
    """Same algorithm, intended for tracking code files in .doc-sync/."""
    return chunk_hash(path_content)
