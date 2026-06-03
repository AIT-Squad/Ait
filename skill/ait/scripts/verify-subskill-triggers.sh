#!/usr/bin/env bash
# verify-subskill-triggers.sh
#
# Lint AIT sub-skills for:
#   1) Description trigger keyword distinctness (no two sub-skills share
#      meaningful >=3-char lowercase tokens, except whitelisted glue words).
#   2) Structural completeness — every SKILL.md must have these H2 sections:
#        - CLI Dependencies (or "Dependencies")
#        - Artifacts
#        - Workflow
#        - Common Pitfalls
#
# Per impl-subskill-trigger-audit (v1.5).
#
# Stdout: human-readable progress; failures via exit 1.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SUB_SKILLS_DIR="$(cd "$SCRIPT_DIR/../sub-skills" && pwd)"

if [ ! -d "$SUB_SKILLS_DIR" ]; then
    echo "❌  sub-skills dir not found: $SUB_SKILLS_DIR" >&2
    exit 1
fi

echo "→ scanning: $SUB_SKILLS_DIR"

# Whitelist tokens:
#   (1) framework / glue words ("ait", "skill", "the", "with"...)
#   (2) AIT core domain nouns intentionally shared across sub-skills
#       ("prd", "impl", "chunk", "chunks") — these label the artifact a
#       sub-skill operates on; cross-skill overlap on them is by design.
#       Differentiation lives in the verb / phase ("write" vs "design"
#       vs "view" vs "execute"), which this audit catches.
WHITELIST="ait skill skills user users when invoke command commands run runs running asks check checks task tasks the for and use uses using subcommand this that with from missing docs file files how prd impl chunk chunks stage"

failures=0

# ── Section 1: structural completeness ──
echo ""
echo "── 1. structural completeness ──"
required_sections=(
    "## CLI Dependencies"
    "## Artifacts"
    "## Workflow"
    "## Common Pitfalls"
)

for skill_md in "$SUB_SKILLS_DIR"/*/SKILL.md; do
    name="$(basename "$(dirname "$skill_md")")"
    missing=()
    for sec in "${required_sections[@]}"; do
        if ! grep -qF "$sec" "$skill_md"; then
            # Allow "## Dependencies" as an alias for "## CLI Dependencies".
            if [ "$sec" = "## CLI Dependencies" ] && grep -qF "## Dependencies" "$skill_md"; then
                continue
            fi
            missing+=("$sec")
        fi
    done
    if [ ${#missing[@]} -eq 0 ]; then
        echo "✓ $name — all sections present"
    else
        echo "❌  $name — missing sections: ${missing[*]}" >&2
        failures=$((failures + 1))
    fi
done

# ── Section 2: trigger keyword distinctness ──
echo ""
echo "── 2. trigger keyword distinctness ──"

# Extract description line per skill into a tmp file: "<name>\t<tokens...>"
TMPFILE="$(mktemp)"
trap 'rm -f "$TMPFILE"' EXIT

for skill_md in "$SUB_SKILLS_DIR"/*/SKILL.md; do
    name="$(basename "$(dirname "$skill_md")")"
    # Pull the description line content (strip "description: " prefix).
    desc="$(grep -m1 '^description:' "$skill_md" | sed 's/^description:[[:space:]]*//' || true)"
    if [ -z "$desc" ]; then
        echo "❌  $name — no description in frontmatter" >&2
        failures=$((failures + 1))
        continue
    fi
    # Lowercase, strip punctuation, take tokens >=3 chars, drop whitelist words.
    tokens="$(echo "$desc" \
        | tr 'A-Z' 'a-z' \
        | tr -c 'a-z0-9-' ' ' \
        | tr -s ' ' '\n' \
        | awk 'length($0) >= 3' \
        | sort -u)"
    # Drop whitelist words.
    filtered=""
    for tok in $tokens; do
        keep=1
        for w in $WHITELIST; do
            if [ "$tok" = "$w" ]; then
                keep=0
                break
            fi
        done
        if [ "$keep" -eq 1 ]; then
            filtered="$filtered $tok"
        fi
    done
    echo -e "$name\t$filtered" >> "$TMPFILE"
done

# Pairwise overlap check (POSIX-compatible — avoids `mapfile` for macOS bash 3.2).
i=0
while IFS=$'\t' read -r name_i toks_i; do
    j=0
    while IFS=$'\t' read -r name_j toks_j; do
        if [ "$j" -le "$i" ]; then
            j=$((j + 1))
            continue
        fi
        overlap=""
        for t in $toks_i; do
            for u in $toks_j; do
                if [ "$t" = "$u" ]; then
                    overlap="$overlap $t"
                fi
            done
        done
        if [ -n "$overlap" ]; then
            echo "❌  trigger overlap: $name_i ⇄ $name_j → [$overlap ]" >&2
            failures=$((failures + 1))
        fi
        j=$((j + 1))
    done < "$TMPFILE"
    i=$((i + 1))
done < "$TMPFILE"

if [ "$failures" -eq 0 ]; then
    # Print a compact distinctness map for log readability.
    echo ""
    echo "── trigger keyword map (post-filter) ──"
    while IFS=$'\t' read -r name toks; do
        printf "  %-22s →%s\n" "$name" "$toks"
    done < "$TMPFILE"
fi

# ── Result ──
echo ""
if [ "$failures" -ne 0 ]; then
    echo "❌  sub-skill trigger audit failed: $failures error(s)" >&2
    exit 1
fi
echo "✅  sub-skill trigger audit passed"
