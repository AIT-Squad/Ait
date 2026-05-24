# Changelog

Notable changes per project version. Software-package versioning lives in [pyproject.toml](pyproject.toml); product-version milestones (v1.0, v1.1, ...) track feature scope.

## v1.1 — 2026-05-24 — Lock AIT working root to `<CWD>/project-docs/`

Tightens AIT's project-root resolution: the only legal working root is `<CWD>/project-docs/`. No `--project` flag, no `AIT_ROOT` env var, no marker-file recursion, no scaffolding fallback. Designed and shipped via AIT's own dogfood loop (PRD `prd-project-docs-only-*` → impl `impl-project-docs-only-root-resolver`, merged to baseline in this release).

### What changed

- New module [skill/ait/ait/root.py](skill/ait/ait/root.py): `resolve_project_root()` + `ProjectRoot` dataclass + `RootResolutionError` hierarchy (3 subclasses)
- [skill/ait/ait/cli.py](skill/ait/ait/cli.py): removed the `--project / -p` CLI option; `main()` now resolves `<CWD>/project-docs/` unconditionally and fails fast on any mismatch
- Tests refactored to use `monkeypatch.chdir(parent)` + `tmp_path/project-docs/` fixtures; the previous pattern of passing `--project <tmp_path>` is gone
- New test file [tests/test_root_resolution.py](tests/test_root_resolution.py) — 8 cases covering all 3 error scenarios plus a non-goal assertion that `AIT_ROOT` env var is ignored
- Documentation updates: [README.md](README.md), [skill/ait/SKILL.md](skill/ait/SKILL.md), [project-docs/README.md](project-docs/README.md) — all layout diagrams now show the `project-docs/` wrapper level and the new error contract

### Error contract

| Code | Trigger |
|---|---|
| `NOT_AT_PROJECT_ROOT` | CWD has no `project-docs/` subdir |
| `PROJECT_DOCS_MALFORMED` | `project-docs/` exists but lacks `docs/` or `.meta/` |
| `CWD_INSIDE_PROJECT_DOCS` | CWD is `project-docs/` itself or any descendant |

All three exit with status 1 and emit the standard JSON failure envelope `{"ok": false, "error": "...", "code": "..."}`.

### Breaking change

Removing `--project / -p` is a CLI breaking change for any caller that was passing a path explicitly. Migration is mechanical: `cd` to the parent of `project-docs/` before invoking `ait`; tests using `CliRunner` should adopt the `monkeypatch.chdir` pattern (see [tests/test_root_resolution.py](tests/test_root_resolution.py) and the refactored [tests/test_e2e_cli.py](tests/test_e2e_cli.py) / [tests/test_reindex.py](tests/test_reindex.py) for reference).

### Tests

66 tests across [tests/](tests/) (up from 58). All green.

## v1.0 — 2026-05-24 (frozen)

Package version: `0.1.0`. MVP closed: single-user, document-side block versioning, Claude Code Skill ready.

### CLI commands (11)

- `ait prd create | save-draft | confirm | show | commit`
- `ait impl create | show | commit`
- `ait version status | merge`
- `ait reindex` — rebuild baseline indexes by rescanning `docs/`
- `ait context` — assemble L1+L2 context for AI prompting

### Architecture

- 13 Python modules (~2700 LOC) under [skill/ait/ait/](skill/ait/ait/) — block_parser, cli, context_assembler, hash_utils, impl_manager, index_manager, io_utils, merge_engine, prd_manager, schemas, validator, version_manager, yaml_io
- Three-stage commit model: working → staged → committed
- Block-level merge with `base_hash` conflict detection
- Only two content types: `prd` and `impl` (ADR / `met-` prefix removed)

### Skill distribution

- [install.py](install.py) — cross-platform installer with `install` / `update` / `uninstall` subcommands; `update` preserves `.venv` for fast upgrades
- [skill/ait/bin/ait](skill/ait/bin/ait), [bin/ait.cmd](skill/ait/bin/ait.cmd) — self-bootstrapping wrappers that create and reuse a per-skill `.venv`

### Dogfooding

- [project-docs/](project-docs/) — AIT's own design docs (3 PRD + 3 impl + auto-built blocks-index.yaml / links-index.yaml) is the **authoritative design source** for v1.0+
- [ait-system.md](.archive/ait-system.md) archived; no longer authoritative

### Tests

58 tests under [tests/](tests/) — block_parser, e2e_cli, index_manager, merge_engine, merge_workflow, prd_impl_context, reindex, version_manager. All green.

### Known limitations of v1.0

- **Slash-command form `/ait:foo` does not route to the skill in Claude Code** — colon namespace is reserved for Claude Code plugin system. v1.0 ships with `/ait` (single-namespace) only.
- No code generation, no code↔doc sync detection, no multi-user collaboration, no `--manual` IDE-jump editing.
