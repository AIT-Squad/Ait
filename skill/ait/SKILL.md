---
name: ait
description: INVOKE THIS SKILL when the user types /ait followed by a subcommand (prd, impl, version, reindex, context). AIT provides block-level version control for AI-collaborated PRD/impl documentation. Treats Markdown blocks (`<!-- @id:xxx -->`) as the version-control unit, supports three-stage commit (working → staged → committed), block-level merge with base_hash conflict detection, baseline reindex from raw markdown, and structured AI context assembly (L1 target block + L2 @ref-related blocks).
---

# AIT — AI-Assisted Document Versioning

AIT (`/ait <subcommand>` commands) is a block-level version control system for AI-collaborated documentation. It is the document-side complement to Git: where Git tracks line-level changes across files, AIT tracks block-level changes across `<!-- @id:xxx -->`-annotated Markdown blocks, with explicit PRD↔impl relations.

## How This Skill Works

**Self-contained**: everything needed lives in this skill directory. The entry point is `bin/ait` (POSIX/Git Bash) or `bin/ait.cmd` (Windows native cmd). On first invocation it creates an isolated `.venv` inside the skill directory and pip-installs the bundled `ait` Python package + its deps. Subsequent runs reuse the venv.

**Invocation convention**: every `ait ...` call in this document refers to `bin/ait` (resolved relative to this skill directory). You can write `bin/ait prd create ...` and let the shell resolve the path; do NOT assume a system-wide `ait` exists.

**Output contract**: every command emits a single JSON object on stdout:

```json
{"ok": true, "data": {...}}                  // success
{"ok": false, "error": "...", "code": "..."} // failure
```

First-time setup messages go to stderr; stdout stays pristine for JSON parsing.

**Slash command form**: users invoke this skill as `/ait` (no colon). Subcommand and arguments follow as plain text — e.g. `/ait prd "新需求标题"`, `/ait reindex`, `/ait version merge v1.1`. The colon-namespaced form `/ait:prd` is NOT supported in skill form (that syntax is reserved for Claude Code's plugin system).

## Project Layout (AIT-managed directory)

AIT resolves its working root by checking for `project-docs/` as a direct subdirectory of the current working directory. The name is hardcoded; there is no override mechanism (no `--root`, no `AIT_ROOT`, no marker-file recursion).

```
<cwd>/                       # ← run `bin/ait` from here, NOT from inside project-docs/
└── project-docs/            # ← hardcoded name; the AIT-managed root
    ├── docs/                # Baseline (source of truth) — flat block index
    │   ├── prd/             # Product Requirements
    │   └── impl/            # Implementation specs
    ├── versions/{vX.Y}/     # Incremental workspaces per version
    │   ├── prd/
    │   └── impl/
    └── .meta/               # Machine-readable indices + records
        ├── config.yaml
        ├── blocks-index.yaml
        ├── links-index.yaml
        ├── blocks-index-{vX.Y}.yaml
        ├── requirements/req-NNN.yaml
        ├── versions/{vX.Y}.yaml
        ├── changes/chg-NNN.yaml
        └── snapshots/{vX.Y}/
```

If the user runs `/ait ...` from a directory that lacks `project-docs/` (or from inside `project-docs/` itself), the CLI exits with a `NOT_AT_PROJECT_ROOT` / `CWD_INSIDE_PROJECT_DOCS` error. **Do not auto-scaffold**; tell the user to either `cd` to the correct parent directory or create the `project-docs/` layout manually:

```bash
mkdir -p project-docs/docs/{prd,impl} \
         project-docs/versions \
         project-docs/.meta/{versions,changes,requirements}
```

## Commands

The MVP exposes 7 core PRD/impl/version commands plus `reindex` and `context` plumbing. Each section below maps a user-facing `/ait <subcommand>` trigger to the underlying `bin/ait` invocation.

### `/ait prd <title>` — Create a new PRD via AI discussion

When the user issues `/ait prd <title>`:

1. **Create the requirement**:
   ```bash
   bin/ait prd create "<title>"
   ```
   Note the `req_id` and `version` from the JSON output.

2. **Enter three-stage AI discussion** (you drive this conversationally):
   - **Clarify** — Ask the user 2-4 focused questions to scope the requirement.
   - **Design** — Propose 3-6 `<!-- @id:prd-... -->` block headings, e.g.:
     ```markdown
     <!-- @id:prd-<slug>-overview -->
     ## 概述

     <!-- @id:prd-<slug>-rules -->
     ## 业务规则
     ```
     Ask user to confirm or adjust.
   - **Generate** — Fill in each block's body. Block IDs MUST follow `{type}-{domain}-{name}` (lowercase, hyphens). For the canonical block format spec, see [references/block-system.md](references/block-system.md).

3. **Save the draft** after discussion converges (use stdin or a tempfile):
   ```bash
   bin/ait prd save-draft <req_id> --content-file -  <<EOF
   <full PRD markdown>
   EOF
   ```

4. **Confirm to version workspace**:
   ```bash
   bin/ait prd confirm <req_id> --file prd/<slug>
   ```
   This writes the markdown into `versions/{v}/prd/<slug>.md` and registers all blocks as `state=working`.

5. Report to the user: requirement ID, version, block count, file path.

### `/ait prd show <prd-file> [block-id]` — View PRD or block

```bash
bin/ait prd show prd/<file-name>          # whole file outline
bin/ait prd show prd/<file-name> <block-id>  # single block content
```

### `/ait prd commit <prd-file>` — Stage + commit the PRD

```bash
bin/ait prd commit prd/<file-name> -m "<message>"
```

This stages every working block belonging to that PRD file and produces a commit (`c1`, `c2`, ...). Each block also emits a `chg-NNN.yaml` record under `.meta/changes/`.

### `/ait impl <prd-block-id>` — Generate impl from a PRD block

When the user issues `/ait impl <prd-block-id>`:

1. **Assemble context** for the AI:
   ```bash
   bin/ait context <prd-block-id> --scenario prd-to-impl
   ```
   This returns the target PRD block (L1) and existing impl examples (L2). Use these to shape your generation.

2. **Generate the impl markdown**. Block IDs must follow `impl-{domain}-{name}`. The system auto-injects a `@ref ... rel:implements` so you do not have to add it yourself, but it doesn't hurt to write it. Default routing by prefix:
   - `impl-api-*` → `impl/api-contracts.md`
   - `impl-data-*` → `impl/data-model.md`
   - `impl-workflow-*` → `impl/workflow.md`

3. **Write the impl into the version workspace**:
   ```bash
   bin/ait impl create <prd-block-id> --content-file - <<EOF
   <!-- @id:impl-api-recommend -->
   ## 推荐接口
   GET /api/v1/recommend ...
   EOF
   ```

4. Report the registered impl block IDs and target file.

### `/ait impl show <impl-block-id>` — View impl block

```bash
bin/ait impl show <impl-block-id>
```

### `/ait impl commit <impl-block-id>` — Stage + commit one impl block

```bash
bin/ait impl commit <impl-block-id> -m "<message>"
```

Pre-condition: the related PRD block must already be `committed` (or live in baseline). The CLI will return an `E1 PRD_NOT_COMMITTED` error otherwise.

### `/ait version merge <vX.Y>` — Merge committed blocks back into baseline

```bash
bin/ait version merge <vX.Y>
bin/ait version merge <vX.Y> --conflict-policy use-version  # force overwrite on hash mismatch
```

- `--conflict-policy abort` (default): if any `base_hash` mismatches the current baseline, stop and report conflicts.
- `--conflict-policy use-version`: force-overwrite baseline with version content (records remain auditable in `chg-NNN.yaml`).
- `--conflict-policy use-baseline`: skip conflicting blocks but commit the rest.

After a successful merge:
- `docs/` is updated with all committed blocks
- `.meta/blocks-index.yaml` is rebuilt
- `.meta/snapshots/{vX.Y}/` captures a snapshot of `docs/`
- The version metadata is marked as merged.

### `/ait reindex` — Rebuild baseline indexes after manual edits

```bash
bin/ait reindex
```

Rescans `docs/` and rewrites `.meta/blocks-index.yaml` + `.meta/links-index.yaml`. Use this after hand-editing baseline markdown (e.g. fixing a typo without going through the version workflow) or when bootstrapping AIT on top of a pre-existing `docs/` layout. Output reports the number of blocks and links indexed.

## Required Knowledge for Driving AIT

All reference docs are bundled inside this skill — no external dependencies:

- **Block format** — [references/block-system.md](references/block-system.md) — canonical `@id` and `@ref` rules
- **Index structure** — [references/index-system.md](references/index-system.md) — baseline vs version index semantics
- **Block parsing algorithm** — [references/block-parser.md](references/block-parser.md) — edge cases and parsing rules
- **Three-stage commit + merge** — [references/version-manager.md](references/version-manager.md) and [references/merge-engine.md](references/merge-engine.md)
- **MVP scope and overview** — [references/overview.md](references/overview.md)

## Common Pitfalls

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `ID_FORMAT` error | Block ID has uppercase / underscores | Force `{type}-{domain}-{name}` with lowercase + hyphens |
| `PRD_NOT_COMMITTED` on impl commit | impl block @ref points at a PRD block still in `working`/`staged` | `bin/ait prd commit <prd-file>` first |
| `MERGE_NO_COMMITTED` on merge | All version blocks are still working/staged | Run `bin/ait prd commit` / `bin/ait impl commit` before merging |
| `BLOCK_NOT_IN_VERSION` | impl block was never registered (likely a file edit bypassing the CLI) | Run `bin/ait reindex` (baseline) or re-run `bin/ait impl create` |
| Conflict on merge | Baseline diverged after the version was forked | Use `--conflict-policy use-version` after reviewing the diff, or rebase manually |
| `NOT_AT_PROJECT_ROOT` on any command | CWD has no `project-docs/` subdir | Tell user to `cd` to the parent directory that contains `project-docs/` (or create the layout, see above) |
| `PROJECT_DOCS_MALFORMED` | `project-docs/` exists but lacks `docs/` or `.meta/` | Create the missing subdir(s) |
| `CWD_INSIDE_PROJECT_DOCS` | User is inside `project-docs/` (or a descendant) | Tell user to `cd ..` out to the parent |
| `PYTHON_MISSING` on first run | No Python 3.10+ on system PATH | Install Python 3.10+ from python.org or your OS package manager |
| `PIP_INSTALL_FAILED` on first run | No internet access | First-time setup requires internet to fetch pyyaml/pydantic/click; subsequent runs are offline |
| `/ait:prd` (colon) doesn't trigger skill | Colon syntax is reserved for Claude Code plugin namespace, not skill form | Use `/ait prd ...` (space-separated) instead |

## MVP Scope Boundaries (Do Not Promise V2 Features)

- `ait` does **not** generate code yet (`/ait impl code` is V2).
- No code↔doc sync detection (`/ait impl sync-status` is V2).
- No multi-user collaboration (single-machine only).
- No `--manual` IDE-jump editing in MVP — for surgical edits ask the user to edit the markdown file directly, then run `bin/ait reindex` to rebuild baseline indexes.
- No colon-namespaced commands (`/ait:foo`) — that syntax is reserved for Claude Code's plugin system; use `/ait foo` (space-separated) instead.

When user asks for any of the above, tell them it's planned for later versions and offer the closest MVP workflow.
