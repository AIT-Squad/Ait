# AIT — AI-Assisted Document Versioning

> Block-level version control for AI-collaborated PRD/impl documentation, packaged as an AI-IDE Skill.

AIT is the document-side complement to Git: it treats Markdown blocks (`<!-- @id:xxx -->`) as the version-control unit, supports three-stage commit (`working → staged → committed`), block-level merge with `base_hash` conflict detection, and structured AI context assembly (L1 + L2).

**Status**: V1.1 frozen on 2026-05-24 — adds hard lock to `<CWD>/project-docs/` as the only legal AIT working root (no `--project` flag, no env override, no marker recursion). Single-user, 11 CLI commands (`prd` / `impl` / `version` / `reindex` / `context`), Claude Code Skill ready. Slash commands invoked as `/ait <subcommand>` (space-separated; colon `/ait:foo` is reserved for Claude Code plugin namespace and not used here). Multi-user collaboration, code generation, marketplace publication, and reverse code↔doc sync are V2.

## Why AIT

When AI collaborates on PRD/impl documents, traditional Git falls short:

- **Line-level diffs don't capture intent.** A PRD is a tree of semantic blocks, not lines.
- **Cross-file relations are invisible.** `impl-api-recommend` implements `prd-book-recommend` — that should be a first-class link, not buried in prose.
- **AI needs structured context, not raw files.** When generating impl from a PRD block, the AI wants exactly that block plus its related impl examples — not the entire repo.

AIT solves this with three primitives: **Block IDs** (`<!-- @id:xxx -->`), **Block references** (`<!-- @ref:... rel:implements -->`), and a **three-stage commit + block-level merge** workflow modeled after Git but operating on blocks instead of lines.

## Install

### As a Claude Code Skill (recommended)

Requires Python 3.10+ on PATH. Internet access needed once for the first invocation.

```bash
git clone <repo-url> ait
cd ait
python install.py                  # fresh install (default; or `install` explicitly)
```

This copies `skill/ait/` into `~/.claude/skills/ait/` and pre-warms the bundled `.venv`. Restart Claude Code and type `/ait prd <title>` in any project that has a `project-docs/` subdirectory to trigger the Skill.

**Upgrade** an existing install (preserves `.venv`, takes <1s):

```bash
cd ait && git pull
python install.py update
```

**Other commands:**

| Command | Effect |
|---------|--------|
| `python install.py install` | Full install — wipes target (including `.venv`) and copies fresh. Re-runs pip install. |
| `python install.py update` | In-place upgrade — overwrites files but keeps `.venv`. Use this after `git pull`. |
| `python install.py uninstall` | Remove the installed skill (asks for confirmation). |
| `--prefix PATH` | Install to a custom directory instead of `~/.claude/skills/ait/`. |
| `--force` | Skip confirmation prompts (`install` / `uninstall` only). |
| `--no-venv-warmup` | Skip the first-run pip install (`install` only). |

Other AI IDEs (Cursor, Continue, Cline) are not officially supported yet — the core CLI works everywhere, but Skill packaging is currently Claude Code-only.

### For development

Requires Python 3.10+ and [`uv`](https://docs.astral.sh/uv/) (or any other PEP 621 installer).

```bash
git clone <repo-url> ait
cd ait
uv venv
uv pip install -e ".[dev]"
uv run pytest                  # 66 tests
uv run ait --help
```

## 5-Minute Quickstart

AIT manages documentation inside a hardcoded `project-docs/` subdirectory at the **current working directory**. From your project root:

```bash
# Bootstrap the project-docs/ wrapper (run once, at your project root):
mkdir -p project-docs/docs/{prd,impl} \
         project-docs/versions \
         project-docs/.meta/{versions,changes,requirements}

# IMPORTANT: every `ait` command runs from THIS directory (the parent of project-docs/).
# Running from inside project-docs/ or any directory without project-docs/ as a direct
# child errors with NOT_AT_PROJECT_ROOT / CWD_INSIDE_PROJECT_DOCS.

ait prd create "图书推荐"
# {"ok": true, "data": {"req_id": "req-001", "version": "v1.0", ...}}

cat > /tmp/recommend-prd.md <<'EOF'
<!-- @id:prd-recommend-overview -->
## 概述

基于借阅历史的图书推荐。

<!-- @id:prd-recommend-rules -->
## 业务规则

不推荐用户已借阅过的图书。
EOF

ait prd save-draft req-001 --content-file /tmp/recommend-prd.md
ait prd confirm req-001 --file prd/recommend
ait prd commit prd/recommend -m "首版推荐 PRD"

cat > /tmp/recommend-impl.md <<'EOF'
<!-- @id:impl-api-recommend -->
## 推荐接口

GET /api/v1/books/recommend → 返回推荐列表。
EOF

ait impl create prd-recommend-overview --content-file /tmp/recommend-impl.md --req-id req-001
ait impl commit impl-api-recommend -m "推荐 API" --req-id req-001

ait version merge v1.0
# project-docs/docs/prd/recommend.md and project-docs/docs/impl/api-contracts.md now
# contain the new blocks.
```

## Command Reference

| Command | Action |
|---------|--------|
| `ait prd create <title>` | Create a requirement; auto-creates a version if none is active |
| `ait prd save-draft <req-id> --content-file <path\|->` | Save AI-discussed PRD markdown into `.meta/requirements/` |
| `ait prd confirm <req-id> --file prd/<slug>` | Materialize the draft into the version workspace |
| `ait prd show <prd-file> [block-id]` | View a PRD file outline or single block |
| `ait prd commit <prd-file> -m <msg>` | Stage + commit every PRD block in that file |
| `ait impl create <prd-block-id> --content-file <path\|->` | Add impl markdown into the version workspace and auto-attach `@ref` |
| `ait impl show <impl-block-id>` | View one impl block |
| `ait impl commit <impl-block-id> -m <msg>` | Stage + commit one impl block (PRD block must already be committed) |
| `ait version status <vX.Y>` | List working / staged / committed counts |
| `ait version merge <vX.Y>` | Merge committed blocks back into the baseline `docs/` |
| `ait reindex` | Rescan `docs/` and rebuild `blocks-index.yaml` + `links-index.yaml` |
| `ait context <block-id> --scenario {prd-to-impl,impl-edit}` | Assemble L1+L2 AI context as JSON |

Every command emits a single JSON object:

```json
{"ok": true, "data": {...}}
{"ok": false, "error": "...", "code": "..."}
```

## Project-Managed Layout

`ait` resolves its working root by checking for `project-docs/` as a direct subdirectory of the current working directory. The name is hardcoded; there is no override mechanism (see [project-docs/docs/prd/project-docs-only.md](project-docs/docs/prd/project-docs-only.md)).

```
<cwd>/                            # ← run `ait` from here, NOT from inside project-docs/
└── project-docs/                 # ← hardcoded name; the AIT-managed root
    ├── docs/                     # baseline — source of truth
    │   ├── prd/
    │   └── impl/
    ├── versions/{vX.Y}/          # per-version incremental workspaces
    │   ├── prd/
    │   └── impl/
    └── .meta/                    # machine-readable indices
        ├── config.yaml
        ├── blocks-index.yaml         # baseline index
        ├── links-index.yaml          # all @ref relations
        ├── blocks-index-{vX.Y}.yaml  # version index (action/state/commit_id)
        ├── versions/{vX.Y}.yaml
        ├── requirements/req-NNN.yaml
        ├── changes/chg-NNN.yaml
        └── snapshots/{vX.Y}/
```

Error codes:

| Code | When |
|---|---|
| `NOT_AT_PROJECT_ROOT` | CWD has no `project-docs/` subdir |
| `PROJECT_DOCS_MALFORMED` | `project-docs/` exists but lacks `docs/` or `.meta/` |
| `CWD_INSIDE_PROJECT_DOCS` | You are inside `project-docs/` (or any of its descendants) |

## Block Format

```markdown
<!-- @id:prd-book-recommend -->
## 图书推荐

基于借阅历史推荐图书。

<!-- @ref:prd/book-management#prd-book-borrow rel:see-also -->
```

- `@id:` is a globally unique block identifier (`{type}-{domain}-{name}`, lowercase + hyphens).
- `@ref:` declares a cross-block link (`implements` / `modifies` / `see-also` plus project-custom rels).
- Blocks are bounded by their `@id` annotation, not by heading levels — so `##` and `###` can be siblings under the same parent.

Full spec: [project-docs/docs/prd/block-system.md](project-docs/docs/prd/block-system.md).

## Three-Stage Commit

```
   working ──stage──► staged ──commit──► committed ──merge──► (baseline)
```

| State | Mutable? | Counts for merge? |
|-------|----------|-------------------|
| working | yes | no |
| staged | yes (back to working) | no |
| committed | no (re-edit creates a new `amends` record) | yes |

Only `committed` blocks land in the baseline at `merge` time.

## AI Context Assembly

`ait context <block-id>` returns a JSON payload structured by relevance:

- **L1** — target block content (never trimmed).
- **L2** — blocks reachable via `@ref` (PRD for impl-edit scenario, related impls for prd-to-impl scenario).
- **L3/L4** — placeholders in MVP; populated in V1.1 (pattern matching) and V2 (project-wide constraints).

The AI is responsible for translating this JSON into a useful prompt; the CLI deliberately does not format prose.

## Testing

```bash
uv run pytest                    # full suite
uv run pytest --cov=src/ait      # with coverage
```

## Documentation

- [project-docs/docs/prd/](project-docs/docs/prd/) — product requirements (dogfooded by AIT itself)
- [project-docs/docs/impl/](project-docs/docs/impl/) — implementation specs for the 3 core modules
- [project-demo/](project-demo/) — example project showing AIT-managed documentation in the wild

`project-docs/` is the authoritative design source; all subsequent design changes go through PRD/impl there first, then code follows.

## License

MIT (see pyproject.toml).
