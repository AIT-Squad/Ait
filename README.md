# AIT — AI-Assisted Document Versioning

**Chunk-level version control for the specs that drive AI coding.**

AIT manages `PRD → FSD → TDD → codegen → code` as one governed pipeline. Design documents
are decomposed into `<!-- @id:... -->` **chunks**; relations between chunks live as explicit
edges in a **SpecGraph**; every generated file is owned by exactly one TDD. The payoff: an AI
agent can be handed a *focused and provably complete* context bundle for any file it is asked
to write, and every artifact traces back to a product requirement.

Ships as a **Claude Code Skill** (`/ait <subcommand>`) over a JSON-only CLI.

---

## The mainline model

```
[PRD]-app ──derives──▶ [FSD]-app                 problem → solution
                          │
                  (internal split)
                          │
              [FSD]-app:core ──decomposes──▶ [FSD]-core    recursive functional tree
                          │
                          └──details──▶ [TDD]-parser       leaf → implementation blueprint
                                             │
                                        target_file: src/parser.py

[FSD]-app:a ──depends_on──▶ [FSD]-app:b          sibling capability dependency
```

Four relation types, four birthplaces. Relations are never inferred from naming and never
hand-written into document bodies:

| Relation | Legal endpoints | Born from |
|---|---|---|
| `derives` | PRD root → root FSD | `fsd create <id> --parent <PRD-root>` |
| `decomposes` | FSD split → child FSD root | `fsd decompose <parent> <child>` |
| `details` | leaf FSD split → TDD root | `tdd create <id> --parent <split>` |
| `depends_on` | two sibling splits under one parent | `depends_on:` yaml block inside `fsd create` content (stripped from disk once the edge exists) |

## Six invariants — enforced, not just documented

| # | Invariant | Violation code |
|---|---|---|
| 1 | Each PRD root maps to exactly one FSD | `PRD_FSD_LINK_NOT_UNIQUE` |
| 2 | Each TDD has exactly one FSD parent and one artifact | `TDD_MULTI_PARENT` / `TDD_TARGET_FILE_REQUIRED` |
| 3 | Each artifact path is owned by exactly one TDD | `DUPLICATE_TARGET_FILE` |
| 4 | Every edge endpoint is a real chunk (no ghost edges) | `MISSING_ENDPOINT` |
| 5 | No orphan chunks outside the spec-tree roots | `ORPHAN_CHUNK` |
| 6 | Every artifact traces TDD → FSD → … → PRD | `TRACE_BROKEN` / `SPEC_CYCLE` |

Two enforcement layers: **write-time gates** reject increments that could never be legal
(ghost endpoint, second TDD parent, artifact collision) with zero disk writes; the
**confirm/merge gate** re-validates the full `baseline ∪ version` view before anything lands.

## Version lifecycle

One open version at a time. The phase machine forces strict top-down authoring:

```
empty ─prd create→ prd-creating ─prd confirm→ prd-confirm
      ─fsd create/decompose→ fsd-creating ─fsd confirm→ fsd-confirm
      ─tdd create→ tdd-creating ─tdd confirm→ tdd-confirm
      ─version merge→ merged
```

- `version create <v>` — the only way to open a version. A second open version is refused
  (`ACTIVE_VERSION_EXISTS`); an existing name is refused (no ghost versions).
- `version commit <v>` — bulk-lock every `working` chunk to `committed`.
- `version confirm <v>` — **pure gate**: six invariants + artifact acceptance + a persisted
  reconciliation plan. Repeatable, zero content writes.
- `version merge <v>` — **the only landing point**: executes the confirmed plan atomically,
  then commits the docs repo. Any failure rolls back byte-for-byte (`MERGE_ROLLBACK`).
- `version revert <v> --confirm` — escape hatch. Unmerged: wipe the workspace. Merged: reset
  the docs repo (and the host repo) to that version's anchor tag.
- Each layer has its own `confirm` / `revert` pair — every gate has a rework path.

## Discussion context & tokens

Calling a `create` command **without content** returns a *discussion background* instead of
writing anything: the relevant existing chunks, pulled along SpecGraph relations, plus a
`context_token`. Content writes must carry that same token, which binds layer, target, parent
anchor, file, action and the actual background it was derived from. Stale or mismatched
tokens are rejected (`CONTEXT_TOKEN_STALE` / `CONTEXT_TOKEN_CONFLICT`). This is a continuity
check, not authentication — `--skip-context` opts out explicitly and leaves an audit trace.

## Docs / code isolation

`project-docs/` is its own Git repository, ignored by the host repo. AIT commits never touch
your code history. `version merge` records the binding: `docs_commit`, `code_base`,
`code_result`, plus a persistent `refs/tags/ait/<v>` revert anchor. Config is layered —
`.meta/config.yaml` is shared and machine-independent, `.meta/config.local.yaml` holds
machine-specific fields (`skill_dir`, `cli_path`, `wrapper_path`, `acceptance_command`) and is
git-ignored. A corrupt config layer raises `CONFIG_UNREADABLE` rather than degrading to `{}` —
gates fail closed.

---

## Install

As a Claude Code Skill (recommended):

```bash
git clone <this-repo> && cd Ait
python install.py                 # installs to ~/.claude/skills/ait
python install.py update          # upgrade, keeps the skill .venv
python install.py uninstall
```

For development:

```bash
uv venv && uv pip install -e ".[dev]"
uv run pytest                     # 362 passing
```

## Quickstart — zero to merged

```bash
mkdir my-project && cd my-project

# 1. Bootstrap. Creates project-docs/ (+ its own git repo), the PRD/FSD roots,
#    the derives edge, empty baseline stores, and the project-local wrapper.
~/.claude/skills/ait/bin/ait init --new-model --name my_project

AIT="project-docs/.ait/ait-cli"        # every later call goes through this

# 2. Open a version.
$AIT version create v0.1

# 3. PRD — discuss first (no --content returns background + context_token), then write.
$AIT prd create "[PRD]-my_project"
$AIT prd create "[PRD]-my_project" --content-file prd.md --action modify \
     --context-token ctx-v1.<digest>
$AIT prd confirm

# 4. FSD — derive the solution tree from the PRD.
$AIT fsd create "[FSD]-my_project" --parent "[PRD]-my_project" --content-file fsd.md \
     --context-token ctx-v1.<digest>
$AIT fsd decompose "[FSD]-my_project:core" "[FSD]-core" --content-file core.md \
     --context-token ctx-v1.<digest>
$AIT fsd confirm

# 5. TDD — one blueprint per target file.
$AIT tdd create "[TDD]-parser" --parent "[FSD]-core:parse" --content-file tdd.md \
     --context-token ctx-v1.<digest>
$AIT tdd confirm

# 6. codegen — get the focused bundle, let the AI write the code.
$AIT codegen prepare "[TDD]-parser"

# 7. Land it.
$AIT acceptance set "uv run pytest -q"     # gates confirm & merge
$AIT version commit v0.1
$AIT version confirm v0.1
$AIT version merge v0.1
```

`codegen prepare` **does not write code**. It returns the TDD body, the upstream chain to the
PRD, the capability contracts of `depends_on` siblings, `target_file` and its current content.
The Skill layer drives the AI from there.

## Command surface

| Group | Commands |
|---|---|
| bootstrap | `init [--new-model --name N] [--check] [--refresh-wrapper] [--skip a,b] [--migrate [--apply]]` |
| prd | `create` · `confirm` · `revert` |
| fsd | `create` · `decompose` · `confirm` · `revert` |
| tdd | `create` · `confirm` · `revert` |
| codegen | `prepare <[TDD]-id>` |
| acceptance | `set "<cmd>"` · `run` |
| version | `create` · `commit` · `confirm` · `merge` · `revert` · `status` |
| specgraph | `sync` · `query` · `export` · `graph-html` · `validate-new-model` |
| query | `state` · `search` · `deps` · `impact` · `context` · `baseline-summary` · `reindex` · `lint` |
| legacy | `prdv1 ...` · `impl ...` · `task ...` · `migrate-block-to-chunk` |

Every command prints exactly one JSON object on stdout:

```json
{"ok": true,  "data": {...}}
{"ok": false, "error": "...", "code": "..."}
```

## Layout

```
<project-root>/                     # run all commands from here
└── project-docs/                   # hard-coded name; its own git repo
    ├── docs/{prd,fsd,tdd}/         # baseline — what merge lands into
    ├── versions/vX.Y/{prd,fsd,tdd}/ + state.md
    ├── .ait/ait-cli                # project-local wrapper (generated, git-ignored)
    └── .meta/
        ├── chunks-index.yaml            # chunk state (baseline)
        ├── chunks-index-vX.Y.yaml       # chunk state (per version)
        ├── specgraph.yaml / -vX.Y.yaml  # chunk relations
        ├── versions/vX.Y.yaml           # phase, plan, git bindings
        ├── config.yaml / config.local.yaml
        └── changes/chg-NNN.yaml
```

`chunks-index` owns *chunk state*; `specgraph` owns *chunk relations*. Both are split into a
baseline file plus one file per version. Never edit `docs/`, `versions/` or `.meta/` by hand —
route everything through the CLI.

## Constraints by design

- Run from the directory *containing* `project-docs/`, never from inside it. No `--project`
  flag, no `AIT_ROOT`, no marker-file search (`NOT_AT_PROJECT_ROOT`, `CWD_INSIDE_PROJECT_DOCS`).
- No system-wide `ait` binary — the project-local wrapper is the entry point (`init` itself is
  the one exception, invoked from the skill directory).
- The CLI never generates business code; it derives context and records state.
- No multi-user locking. Single-writer model.
- `chunk delete` is not implemented — `add` / `modify` cover current needs.
- The legacy `prdv1 → impl → task` pipeline still runs but is frozen.

## Docs

| File | Contents |
|---|---|
| [USER_GUIDE.md](USER_GUIDE.md) | Task-oriented walkthrough, per-command reference, troubleshooting |
| [DESIGN.md](DESIGN.md) | Architecture, design rationale, module map |
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [skill/ait/SKILL.md](skill/ait/SKILL.md) | Skill contract — authoritative command routing |
| [skill/ait/references/new-model-format.md](skill/ait/references/new-model-format.md) | **Authoritative** PRD/FSD/TDD format spec |
| [skill/ait/templates/](skill/ait/templates/) | Document skeletons shipped with the skill |

## Dogfooding

AIT is built with AIT. [project-docs/](project-docs/) holds its own PRD (16 chunks), 17 FSD
files and 46 TDD files — each TDD owning exactly one source, test, reference or template file.
Every release since v2.0 went through the full `version create → prd → fsd → tdd → codegen →
confirm → merge` loop. `project-docs-v1/` is the archived legacy-model baseline.

MIT licensed.
