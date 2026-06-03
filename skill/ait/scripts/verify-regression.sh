#!/usr/bin/env bash
# verify-regression.sh — End-to-end regression on real project-docs/.
# Layer 2 (functional) acceptance script for v1.2.
# Exit 0 = passed, Exit 1 = failed.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# 0. Sanity: imports work
echo "→ checking imports..."
python3 -c "from ait import schemas, chunk_parser, migrations" >/dev/null

# 1. Migrate existing .meta/ data (idempotent)
echo "→ migrating .meta/ (idempotent)..."
python3 -m ait.cli migrate-block-to-chunk >/dev/null

# 2. PRD-side smoke
echo "→ smoke: version status v1.2..."
python3 -m ait.cli version status v1.2 >/dev/null

# 3. Context smoke (PRD-to-impl)
echo "→ smoke: context prd-skills-rename-block-to-chunk..."
python3 -m ait.cli context prd-skills-rename-block-to-chunk --scenario prd-to-impl >/dev/null

echo "✅  regression passed"
