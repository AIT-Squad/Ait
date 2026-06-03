# AIT — AI-Assisted Document Versioning

> Chunk-level version control for AI-collaborated PRD/impl documentation, packaged as an AI-IDE Skill — now with a full `prd → impl → task → code` pipeline.

AIT is the document-side complement to Git: it treats Markdown chunks (`<!-- @id:xxx -->`) as the version-control unit, supports three-stage commit (`working → staged → committed`), chunk-level merge, structured AI context assembly, and — as of the redesign — a complete AI-coding pipeline that turns locked PRD+impl into executable task YAML.

**Status**: Redesign (the `prd-impl-task` three-state pipeline) implemented and dogfooded through v1.5 (skill/CLI resolution, sub-skills coverage, task relocation, init incremental). Single-user, Claude Code Skill. Slash commands invoked as `/ait <subcommand>` (space-separated). Multi-user collaboration and marketplace publication remain future work.

> **CLI invocation (v1.5+)**: every `ait ...` example below means the project-local wrapper `project-docs/.ait/ait-cli`, generated automatically by `ait init`. The only place you call the system-level entry `~/.claude/skills/ait/bin/ait` is the very first `init` (or `init --refresh-wrapper` after the skill is reinstalled to a different path). Do **not** use a relative `bin/ait` from the project root — it does not exist there.

## The Pipeline at a Glance

```
/ait init                     bootstrap global baseline (fresh) OR diff-fill missing files (incomplete) — ready projects no-op
        │
        ▼
/ait prd create "<title>"     discuss → write PRD chunks (four-section structure)
/ait prd confirm  ───────────▶ write to version workspace
/ait prd commit   ───────────▶ LOCK the PRD (frozen for this version)
        │
        ▼
/ait impl create <prd-chunk>  design implementation (1 PRD chunk → N impl chunks)
/ait impl commit  ───────────▶ pre-merge check (cycle + intra-version dup) → LOCK impl
        │
        ▼
/ait task create <prd-chunk>  derive AI-coding task YAML from specgraph (impl_refs + global_refs + deps)
/ait task execute <id>        emit token-focused context bundle → AI codes
/ait task complete <id>       self-close: mark done + bind code_refs (git commit / file paths)
        │
        ▼
/ait version confirm <vX.Y>   precheck (all tasks done + git clean) → merge to baseline
                               → extract dynamic global from impl @extract → git commit (msg = title)
```

The whole version is an **atomic unit**: once a PRD/impl is committed it is immutable. The only escape hatch is `/ait version reset <vX.Y>` — wipe the version workspace and start over (no partial undo).

## Why AIT

When AI collaborates on PRD/impl documents, traditional Git falls short:

- **Line-level diffs don't capture intent.** A PRD is a tree of semantic chunks, not lines.
- **Cross-file relations are invisible.** `impl-api-recommend` implements `prd-book-recommend` — that should be a first-class link.
- **AI needs focused context, not raw files.** When coding a task, the AI wants exactly its impl chunks + global constraints — not the whole repo. AIT's `task execute` hands the AI a minimal bundle (impl_refs ∪ global_refs), which is the core of its token-efficiency.

AIT solves this with: **Chunk IDs** (`<!-- @id:xxx -->`), **Chunk references** (`<!-- @ref:... rel:implements -->`), **extract markers** (`<!-- @extract:dynamic/ddl#pet -->`), a **three-stage commit**, and a **specgraph** that records all chunk relations.

## Install

### As a Claude Code Skill (recommended)

Requires Python 3.10+ on PATH. Internet access needed once for the first invocation.

```bash
git clone <repo-url> ait
cd ait
python install.py                  # fresh install
```

This copies `skill/ait/` into `~/.claude/skills/ait/` and pre-warms the bundled `.venv`. Restart Claude Code and type `/ait init` (or `/ait prd <title>`) in any project that has a `project-docs/` subdirectory.

**After the first `/ait init`** the project gets a thin local wrapper at `project-docs/.ait/ait-cli` that delegates to the installed skill. From that moment on, every project-side command (manual or skill-invoked) uses the wrapper — `init` is the only command that may be invoked through the system-level `bin/ait`. If you ever reinstall the skill to a different prefix, run `~/.claude/skills/ait/bin/ait init --refresh-wrapper` to point the wrapper at the new path.

> **macOS note**: if the bundled venv fails to load native wheels (`dlopen ... different Team IDs`), rebuild the venv with Homebrew Python (`/opt/homebrew/bin/python3.13 -m venv ...`) instead of a hardened-runtime Python.

**Upgrade** (preserves `.venv`):

```bash
cd ait && git pull && python install.py update
```

| Command | Effect |
|---------|--------|
| `python install.py install` | Full install — wipes target (including `.venv`), copies fresh, re-runs pip install. |
| `python install.py update` | In-place upgrade — overwrites files, keeps `.venv`. Use after `git pull`. |
| `python install.py uninstall` | Remove the installed skill. |
| `--prefix PATH` | Install to a custom directory. |
| `--force` | Skip confirmation prompts. |
| `--no-venv-warmup` | Skip first-run pip install. |

### For development

```bash
git clone <repo-url> ait && cd ait
uv venv && uv pip install -e ".[dev]"
uv run pytest
uv run ait --help
```

## Quickstart — the full loop

AIT manages documentation inside a hardcoded `project-docs/` subdirectory at the **current working directory**. Every `ait` command runs from the parent of `project-docs/`.

```bash
# 0. Bootstrap the global baseline (run once per project; refused if already managed).
ait init
# Creates docs/global/{overview,tech-stack}.md (static) + {ddl,schema,api}.md (dynamic skeletons).

# 1. PRD — discuss, write, lock.
ait prd create "宠物建档"
cat > /tmp/pet-prd.md <<'EOF'
<!-- @id:prd-pet-archive -->
## 宠物建档

### 概述
宠物档案创建。

### 业务规则
- 名称必填

### 验收标准
- [ ] 能创建档案并持久化

### 边界与非目标
- 不做跨用户共享
EOF
ait prd save-draft req-001 --content-file /tmp/pet-prd.md
ait prd confirm req-001 --file prd/pet
ait prd commit  prd/pet -m "宠物建档 PRD"      # ← locks the PRD

# 2. impl — design implementation, mark extractable fragments, lock.
cat > /tmp/pet-impl.md <<'EOF'
<!-- @id:impl-pet-archive-ddl -->
## 宠物档案数据模型

软删除 + OSS key。

<!-- @extract:dynamic/ddl#pet -->
```sql
CREATE TABLE pet (id BIGINT PRIMARY KEY, name VARCHAR(50) NOT NULL);
```
<!-- @extract-end -->
EOF
ait impl create prd-pet-archive --content-file /tmp/pet-impl.md
ait impl commit impl-pet-archive-ddl -m "数据模型"   # ← pre-merge check, then locks impl

# 3. task — derive, execute, self-close.
ait task create prd-pet-archive          # → T-pet-archive-01 (impl_refs / global_refs / deps)
ait task execute T-pet-archive-01        # → emits focused context bundle for the AI
# ... AI writes code, then:
ait task complete T-pet-archive-01 --commit <hash> --path src/pet.py

# Aside (v1.5): task YAML lives at versions/<v>/tasks/T-*.yaml — co-located with the version it serves.
# A summary of all tasks in a version is also indexed at .meta/versions/{vX.Y}.yaml#tasks_summary.

# 4. version confirm — merge to baseline + extract dynamic global + git commit.
ait version confirm v1.0
# docs/ gets the chunks, docs/global/ddl.md gets the extracted `pet` table,
# and a git commit lands with message = the version title.
```

## Command Reference

### Global / lifecycle

| Command | Action |
|---------|--------|
| `ait init` | Bootstrap or diff-fill the global baseline (`docs/global/*`). Three modes auto-detected: **fresh** (creates everything), **incomplete** (only fills missing files / config — never touches existing user content), **ready** (no-op). Use `--check` for a dry-run report and `--skip <file>` to opt out of specific files. Does not consume a version number. |
| `ait reindex` | Rescan `docs/`; rebuild `chunks-index.yaml` + baseline `specgraph.yaml`. |
| `ait state [--version vX.Y] [--save]` | Render the version progress panel (title, phase, lock flags, impl coverage, task progress). `--save` writes `versions/<v>/state.md`. |

### PRD

| Command | Action |
|---------|--------|
| `ait prd create <title>` | Create a requirement; auto-creates a version if none is active. |
| `ait prd save-draft <req-id> --content-file <path\|->` | Save AI-discussed PRD markdown into `.meta/requirements/`. |
| `ait prd confirm <req-id> --file prd/<slug>` | Materialize the draft into the version workspace (writes + refreshes `state.md`). |
| `ait prd show <prd-file> [chunk-id]` | View a PRD file outline or one chunk. |
| `ait prd commit <prd-file> -m <msg>` | Stage + commit PRD chunks **and lock the PRD** for this version. |

### PRD additional commands

| Command | Action |
|---------|--------|
| `ait prd resolve-candidates --from-file <yaml>` | Persist skill-produced PRD candidate decisions into the active version workspace. |

### impl

| Command | Action |
|---------|--------|
| `ait impl create <prd-chunk-id> --content-file <path\|->` | Add impl markdown; auto-attach `@ref ... rel:implements`. One PRD chunk → N impl chunks. Refused if impl is locked. |
| `ait impl show <impl-chunk-id>` | View one impl chunk. |
| `ait impl commit <impl-chunk-id> -m <msg>` | Stage + commit; runs **pre-merge check** (dependency cycle + intra-version duplicate `@id`/`@extract` target). Source PRD chunk must already be committed. |

### Impl additional commands

| Command | Action |
|---------|--------|
| `ait impl inherit <prd-chunk-id>` | Copy baseline impl chunks for a PRD into the active version workspace (reuse in incremental versions). |
| `ait impl lock [--version <v>]` | Lock impl for the version, advancing phase to `impl_locked` (must run after all impl chunks are committed). |

### task

| Command | Action |
|---------|--------|
| `ait task create [prd-chunk]` | Derive task YAML(s) from the PRD chunk's impl coverage (via specgraph). No id → list PRD chunks still pending a split. |
| `ait task list [--version vX.Y]` | List tasks with status / source_chunk / deps. |
| `ait task show <task-id>` | Show a full task YAML. |
| `ait task execute [task-id\|prd-chunk]` | Mark task(s) `executing` and emit the focused context bundle (impl_refs ∪ global_refs only). Dependency-gated. No selector → all pending. |
| `ait task complete <id> [--commit <hash>] [--path <p> ...]` | Mark `done` + bind `code_refs`. This is execute's self-close — there is no `task confirm`. |
| `ait task fail <task-id>` | Mark `failed` (re-runnable via `execute`). |

### version

| Command | Action |
|---------|--------|
| `ait version status <vX.Y>` | working / staged / committed counts. |
| `ait version confirm <vX.Y> [--allow-dirty-git]` | Atomic: precheck (all tasks `done` + git clean) → merge to baseline → extract dynamic global from impl `@extract` → promote specgraph → git commit (message = version title). Rolls back `docs/` if anything fails. |
| `ait version merge <vX.Y>` | Low-level merge of committed chunks into baseline (`confirm` calls this internally). |
| `ait version reset <vX.Y> --confirm` | **Escape hatch**: physically delete the version workspace + indices + `specgraph-{v}.yaml` + tasks. Merged versions cannot be reset. |

### Query / graph

| Command | Action |
|---------|--------|
| `ait deps <chunk-id>` | Outgoing dependencies (implements / depends-on) from specgraph. |
| `ait impact <chunk-id>` | Reverse-reachable chunks (what breaks if this changes). |
| `ait specgraph sync` | Rebuild specgraph from `docs/` + version workspaces. |
| `ait specgraph add-edge <src> <dst> --rel <rel>` | Manually add an edge to the specgraph. |
| `ait specgraph query <chunk-id> [--deps\|--implements]` | Query the relation graph. |
| `ait specgraph export [--format dot]` | Export the graph (Graphviz DOT). |
| `ait context <chunk-id> --scenario {prd-to-impl,impl-edit}` | Assemble L1+L2 AI context as JSON. |
| `ait search <query>` | Full-text search across chunks. |

### Lint / maintenance

| Command | Action |
|---------|--------|
| `ait lint [--scope {baseline,version,vX.Y}] [--fix]` | Validate PRD (four sections) / impl (`@ref` integrity) formatting. `--fix` auto-fills missing PRD sections. |
| `ait baseline-summary [--scope {prd,impl,all}] [--format {yaml,json}]` | List baseline chunk summaries (useful for prompt budgeting). |
| `ait reindex` | Rebuild baseline `chunks-index.yaml` + `specgraph.yaml` from `docs/`. Also refreshes per-version `tasks_summary`. |
| `ait migrate-block-to-chunk [--dry-run]` | One-time v1.1→v1.2 data migration (rename `block` → `chunk` in `.meta/*.yaml`). |

Every command emits a single JSON object: `{"ok": true, "data": {...}}` or `{"ok": false, "error": "...", "code": "..."}`.

## Project-Managed Layout

`ait` resolves its working root by checking for `project-docs/` as a direct subdirectory of the current working directory. The name is hardcoded; there is no override.

```
<cwd>/                              # ← run `ait` from here, NOT inside project-docs/
└── project-docs/
    ├── docs/                       # baseline — source of truth
    │   ├── prd/
    │   ├── impl/
    │   └── global/                 # init-generated: overview, tech-stack (static)
    │       │                       #                 ddl, schema, api (dynamic, from @extract)
    │       └── ...
    ├── versions/{vX.Y}/            # per-version incremental workspaces
    │   ├── prd/  ├── impl/  ├── tasks/T-*.yaml  └── state.md
    └── .meta/                      # machine-readable indices
        ├── config.yaml
        ├── chunks-index.yaml           # baseline chunk台账
        ├── chunks-index-{vX.Y}.yaml    # version chunk台账 (action/state/commit_id)
        ├── specgraph.yaml              # baseline relation graph
        ├── specgraph-{vX.Y}.yaml       # per-version relation graph (split-file)
        ├── versions/{vX.Y}.yaml        # version meta (phase / locks / title / tasks_summary)
        # task YAMLs live at versions/{vX.Y}/tasks/T-*.yaml (v1.5 — co-located with the version)
        ├── requirements/req-NNN.yaml
        ├── changes/chg-NNN.yaml
        └── snapshots/{vX.Y}/
```

> **`links-index.yaml` is deprecated.** All chunk relations now live in `specgraph`. See "Two indices" below.

Error codes: `NOT_AT_PROJECT_ROOT`, `PROJECT_DOCS_MALFORMED`, `CWD_INSIDE_PROJECT_DOCS`, `PRD_NOT_COMMITTED`, `LOCKED` (writing a locked PRD/impl), `PREMERGE_FAILED`, `TASK_NOT_DONE` / `GIT_DIRTY` (version confirm precheck), `MERGE_ROLLBACK`.

> Shell-level pitfall (not a CLI return code): if you see `zsh:1: no such file or directory: bin/ait`, you are calling a non-existent relative path. Switch to `project-docs/.ait/ait-cli <subcmd>`. AIT documents this as `ENOENT_BIN_AIT` for traceability; it is **not** registered in `ait/schemas.py` and never reaches `ait-resume`.

## Two indices: chunks-index vs specgraph

Both index the **same chunks** but from different angles:

| | `chunks-index-{v}.yaml` | `specgraph[-{v}].yaml` |
|---|---|---|
| **Manages** | each chunk's own **state** | relations **between** chunks |
| **Shape** | flat list (state / action / commit_id / file) | directed graph (specs + `implements`/`depends-on` edges) |
| **Answers** | "what stage is this chunk at?" | "what implements / depends on this chunk?" |
| **Consumed by** | `version status` / `commit` / `merge` | `task create` (impl_refs), `deps` / `impact` / pre-merge cycle check |

Both follow the same split-file convention: one global baseline file + one per version (`{name}-{v}.yaml`), so `version reset` is a clean `rm`.

## Chunk & extract format

```markdown
<!-- @id:impl-pet-archive-ddl -->
## 宠物档案数据模型

设计说明（纯文本，不提取）。

<!-- @extract:dynamic/ddl#pet -->
```sql
CREATE TABLE pet (id BIGINT PRIMARY KEY, name VARCHAR(50) NOT NULL);
```
<!-- @extract-end -->

<!-- @ref:prd/pet#prd-pet-archive rel:implements -->
```

- `@id:` — globally unique chunk id (`{type}-{domain}-{name}`, lowercase + hyphens).
- `@ref:` — cross-chunk link (`implements` / `depends-on` / `refines` / `see-also`).
- `@extract:dynamic/{type}#{chunk} ... @extract-end` — marks a fragment that `version confirm` extracts into `docs/global/{type}.md` (DDL / schema / api). **Dynamic global content comes ONLY from impl `@extract`** — never edit it by hand.

Full spec: [project-docs/docs/impl/chunk-system.md](project-docs/docs/prd/chunk-system.md).

## PRD chunk structure (four sections)

PRD chunks use a fixed structure so tasks split cleanly:

```markdown
<!-- @id:prd-xxx -->
## 标题
### 概述            # one-line value
### 业务规则        # the basis for splitting tasks
### 验收标准        # the done-criteria for tasks
### 边界与非目标     # prevents AI over-reach
```

## Three-Stage Commit + version atomicity

```
working ──stage──► staged ──commit──► committed ──confirm/merge──► baseline
```

| State | Mutable? | Counts for merge? |
|-------|----------|-------------------|
| working | yes | no |
| staged | yes (back to working) | no |
| committed | no — **locks the PRD/impl** | yes |

A version is all-or-nothing: there is no partial undo. To change anything after a commit, `version reset` and rebuild.

## Testing

```bash
uv run pytest                    # full suite
# Against skill source with the bundled venv:
PYTHONPATH=skill/ait .codebuddy/skills/ait/.venv/bin/python -m pytest tests/ -q
```

## Sub-skills

AIT routes specific workflows to focused sub-skills under `skill/ait/sub-skills/`:

| Sub-skill | Trigger | Purpose |
|---|---|---|
| `ait-discuss` | `/ait prd <title>` | Three-stage PRD discussion (Clarify → Design → Generate) and CLI persistence. |
| `ait-impl-discuss` | `/ait impl <prd-chunk-id>` | Plan/generate impl chunks (with `@extract`) and register them via CLI. |
| `ait-state` | `/ait state` / progress queries / task list | Render version state.md and answer chunk-three-state / impl-coverage / task-status questions in one place. |
| `ait-resume` | CLI returns an error code | Map JSON `code` to recovery steps (including `version reset` guidance). |
| `ait-init-guide` | `init` enters incomplete mode | Walk through global-file diff fill; the CLI itself decides fresh/incomplete/ready, the skill no longer pre-classifies. |
| `ait-task-execute` | `/ait task execute <id>` | Drive AI coding from the focused context bundle and call `task complete/fail`. |

## Documentation

- [project-docs/docs/prd/](project-docs/docs/prd/) — product requirements (dogfooded by AIT itself; see `ait-redesign.md`).
- [project-docs/docs/impl/](project-docs/docs/impl/) — implementation specs.
- `project-docs/` is the authoritative design source; design changes go through PRD/impl there first, then code follows.

## License

MIT (see pyproject.toml).
