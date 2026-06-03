#!/usr/bin/env bash
# verify-no-block-leak.sh — Verify no 'block' identifier leaks after the chunk rename.
# Layer 1 (grep-based) acceptance script for v1.2.
# Exit 0 = clean, Exit 1 = leak detected.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Layer 1a: Python source code — must be 0 (allow natural English + migration-tool literals)
PY_HITS=$(grep -rIn -E '\bblock\w*|\bBlock\w*' \
            "$ROOT/ait/" \
            --include='*.py' \
            | grep -v '# noqa: chunk-rename' \
            | grep -vE '\bblocking\b|\bunblock\b|\bnon-blocking\b|blocks the operation|block style' \
            | grep -vE 'block-system\.md|block-parser\.md' \
            | grep -v 'migrations.py' \
            | grep -v 'migrate-block-to-chunk' \
            | grep -v "rename .block. to .chunk." \
          || true)
PY_COUNT=$(printf '%s' "$PY_HITS" | grep -c '^' || true)

# Layer 1b: SKILL.md and references/ — must be 0 (term sense)
DOC_HITS=$(grep -rIn -E '\bblock\w*|\bBlock\w*' \
             "$ROOT/SKILL.md" "$ROOT/references/" \
             --include='*.md' \
             | grep -v 'noqa: chunk-rename' \
             | grep -vE 'code block|blocking|unblock|non-blocking' \
           || true)
DOC_COUNT=$(printf '%s' "$DOC_HITS" | grep -c '^' || true)

if [ "$PY_COUNT" -ne 0 ] || [ "$DOC_COUNT" -ne 0 ]; then
  echo "❌  block-leak detected"
  echo "--- Python ($PY_COUNT) ---"
  printf '%s\n' "$PY_HITS"
  echo "--- Docs ($DOC_COUNT) ---"
  printf '%s\n' "$DOC_HITS"
  exit 1
fi

echo "✅  no block-identifier leak"
