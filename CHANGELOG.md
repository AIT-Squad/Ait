# Changelog

Notable changes per project version. Software-package versioning lives in [pyproject.toml](pyproject.toml); product-version milestones (v1.0, v1.1, ...) track feature scope.

> **v1.2–v1.6 为事后补录**：这几版通过 AIT 自身的 dogfood 流程开发，变更当时记录在 `project-docs/.meta/changes/` 而非本文件。下列条目据此还原，每条标注其 `chg-*` 区间，chunk 级细节见对应记录。

## v1.6 — 2026-06-03 — Baseline PRD 单文件化 + 格式硬约束

把 baseline PRD 物理布局从 `docs/prd/*.md` 多文件统一为 `docs/prd/global.md` 单文件，并引入格式硬约束闸门。chunk 仍是唯一规划/合并单位，impl 保持多文件。

### What changed

- **Baseline PRD 单文件化**：新契约 `docs/prd/global.md`；一次性迁移脚本（dry-run/apply + 7 步自检），迁移前后 chunk 数 / id 集合 / `@ref` 关系图全等校验。
- **merge 路由收敛**：`version_manager` 把版本工作区任意 `prd/*.md` 的 chunk 在 confirm/merge 时统一缝合进 `prd/global`；版本工作区仍可多文件。
- **格式硬约束**：格式闸门 + `ait lint --fix` + 派生命名校验。
- **新增能力**：`baseline-summary` 命令 + chunks-index `summary` 字段 + `@summary` 注释；`prd create` 递归扫 baseline + candidates 决议 + commit overrides 校验；PRD chunk 原子 impl 替换 + 覆盖率守卫 + `impl inherit` + `@prd-no-impl`。
- 单文件 baseline 兼容性回归测试网；已 merged 的 v1.1~v1.5 历史快照与 `chunks-index-{v}` 保持不动。

> 12 changes（chg-080~091）。版本 meta 的 `title` 字段为 null（故 git commit 落为默认 `feat: v1.6`）；本标题为补录。

## v1.5 — 2026-06-02 — task relocation, init incremental, skill CLI resolution, sub-skills coverage

（标题取自 `.meta/versions/v1.5.yaml`。）围绕 task 资产归位、init 增量化、skill CLI 路径解析、sub-skills 覆盖四条线推进。

### What changed

- **task relocation**：task YAML 从 `.meta/tasks/{v}/` 迁到 `versions/{v}/tasks/`（与 prd/impl/state.md 同处版本工作区）；`tasks_summary` 写入 `chunks-index-{v}.yaml`；legacy `.meta/tasks` 路径启动告警。
- **init incremental**：init 三态检测（fresh / incomplete / ready）+ `--check` dry-run；`ait-init-check` 改名 `ait-init-guide` 并重写 workflow。
- **skill CLI resolution**：init 注入 `skill_dir` 并生成 project-local wrapper `project-docs/.ait/ait-cli`；所有文档 `bin/ait` 引用改为该 wrapper；新增 wrapper self-locate 回归脚本与 `ENOENT_BIN_AIT` pitfall 说明。
- **sub-skills coverage**：新增 `ait-task-execute`；`ait-progress` 并入 `ait-state`；sub-skill 触发 lint + section 审计。

> 17 changes（chg-063~079）。

## v1.4 — 2026-06-01 — prd → impl → task 三态流水线重构（redesign 落地）

AIT 重构为围绕 **prd → impl → task** 三核心态的版本化 AI 开发流水线——README 所称 redesign 的设计定稿与落地。

### What changed

- **三核心态**：PRD（需求意图）→ impl（实现设计）→ task（AI coding 执行单元），逐级派生；全程 chunk 聚焦以最小化 token。
- **版本原子性**：任一 confirm 后内容在本版本内冻结，不可局部修改/撤销/回滚；唯一逃生口 `version reset`（二次确认 + 物理删除版本工作区 / 索引 / specgraph 分文件，无快照）。
- **简化**：取消局部回滚、单 chunk 放弃、checksum 失效检测、增量版本继承等子系统（被版本原子性取代）。
- 8 块重构 PRD（`prd/ait-redesign`）+ 对应 impl（`impl/core` 等）设计定稿。

> 24 changes（chg-039~062）。

## v1.3 — 2026-05-30 — SpecGraph + sub-skill 体系 + 检索/图谱命令

把关系索引从 `links-index.yaml` 重构为 SpecGraph，落地 sub-skill 体系，并迁入一批检索/图谱命令。

### What changed

- **SpecGraph**：`links-index.yaml` → SpecGraph 关系图模型 + CLI（baseline + per-version 分文件）。
- **sub-skill 体系**：主 SKILL.md 改造为 router；落地 sub-skill layout / format / mapping / contract、micro-skill overview 与 skill migration；新增 `ait-state` skill。
- **新命令**：`search`、`deps`、`impact`、`state` 面板（部分自参考项目 skill 功能迁移）。
- **init 智能识别**：init 流程按项目状态自适应。

> 22 changes（chg-017~038）。

## v1.2 — 2026-05-25 — micro-skill 拆分 + block → chunk 术语重构

把 monolithic SKILL.md 沿"用户所处阶段"拆为 router + 多个 micro-skill；并把全局术语从 `block` 重命名为 `chunk`。

### What changed

- **micro-skill 拆分**：主 SKILL.md 改为 router（全局速查 + Common Pitfalls + sub-skills 索引），具体流程下沉子 skill；子 skill 不引入新 CLI、不直接读写 `docs/` 与 `.meta/`。
- **block → chunk 重构**：代码符号 + 文档 + schema + 索引文件常量全面重命名；一次性数据迁移脚本（即 `migrate-block-to-chunk`）+ 双验证脚本（防术语泄漏 / 回归）。

> 10 changes（chg-007~016；req-002）。

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
