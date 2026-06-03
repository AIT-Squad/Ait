---
name: ait-state
description: INVOKE THIS SKILL when the user asks to view AIT version state, refresh state.md, check version progress, chunk three-state distribution, impl coverage, or task counts.
---

# ait-state

## Purpose

展示或刷新版本状态面板，并兼任进度查询入口：帮助用户快速了解 PRD/impl chunk 三态分布、实现覆盖、task 状态以及下一步工作。

## CLI Dependencies

- `project-docs/.ait/ait-cli state [--version <v>]` — 渲染 ASCII 面板
- `project-docs/.ait/ait-cli state [--version <v>] --format json` — 机器可读状态摘要
- `project-docs/.ait/ait-cli state [--version <v>] --save` — 落盘 `versions/<v>/state.md`
- `project-docs/.ait/ait-cli version status <v>` — 补充查 phase / lock 位
- `project-docs/.ait/ait-cli task list --version <v>` — 枚举 task（进度查询场景）
- `project-docs/.ait/ait-cli task show <id>` — 查看单个 task 详情

## Artifacts

- **Reads**：`.meta/versions/<v>.yaml`、`.meta/chunks-index-<v>.yaml`、`.meta/specgraph.yaml`、`versions/<v>/tasks/T-*.yaml`。
- **Writes**：只通过 `project-docs/.ait/ait-cli state --save` 写入 `versions/<v>/state.md`。
- **Side-effect**：刷新状态面板。

## Workflow

### A. State 渲染
1. 确认目标版本；用户未指定时使用当前未 merged 版本。
2. 查看状态：调用 `state --version <v>`。
3. 需要机器可读摘要：调用 `state --version <v> --format json`。
4. 需要落盘：调用 `state --version <v> --save`。
5. 向用户摘要三态分布、PRD→impl 覆盖、未完成项。

### B. 进度查询
1. 用户问“版本进度”/“chunk 三态分布”/“task 状态”时，优先调 `state --version <v> --format json`。
2. 从 JSON 中读 `counts` / `working` / `staged` / `committed` / `impl_coverage` / `tasks_summary` 五段。
3. 输出结构化 ASCII 摘要：总计 / chunk 三态 / impl 覆盖率 / task 计数。
4. 若 state 命令不可用，回退 `version status <v>` + `task list --version <v>` 拼凑。

### C. 任务清单
1. 用户问“task 跑到哪了” / “哪些 task 未完成”：调 `task list --version <v>`。
2. 查看单个 task 详情：调 `task show <id>`。
3. 优先从 `tasks_summary` 字段取计数，避免重复列举。

## Output Contract

不要原样 dump Markdown 或 JSON；只摘要版本、计数、覆盖率、未完成 chunk、task 状态和保存路径。进度表述采用 `done / total` + ASCII 进度条。

## Common Pitfalls

- `NO_VERSION`：没有当前版本，要求用户指定 `--version` 或先创建版本。
- `NOT_AT_PROJECT_ROOT`：切换到包含 `project-docs/` 的项目根。
- `PROJECT_DOCS_MALFORMED`：修复缺失目录后重试。
- `specgraph.yaml` 缺失：先执行 `project-docs/.ait/ait-cli specgraph sync` 或 `project-docs/.ait/ait-cli state --save` 自动刷新。
- 用户问“哪些 chunk 还没 impl”：用 `--format json` + `impl_coverage` 字段筛 missing。
- 用户问“task 进度”：用 `tasks_summary` 字段（由 `impl-task-summary-index` 提供）。