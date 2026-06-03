---
name: ait-task-execute
description: INVOKE THIS SKILL when the user runs /ait task execute or asks to start coding a specific task; orchestrates context bundle → AI coding → task complete/fail.
---

# ait-task-execute — drive AI coding for a single task

## Trigger

- `/ait task execute T-xxx-NN`
- "帮我跑一下 T-xxx-NN" / "开始编码 task T-xxx" 等中文等价请求
- 用户已 `/ait task create` 派生出 task 后，要求"接下来执行"

## CLI Dependencies

- `project-docs/.ait/ait-cli task execute <id>` — 标 executing + 输出聚焦 context bundle
- `project-docs/.ait/ait-cli task complete <id> --commit <hash> --path <files>` — 收口
- `project-docs/.ait/ait-cli task fail <id>` — 失败回退（可重跑 execute）
- `project-docs/.ait/ait-cli task show <id>` — 查 steps / impl_refs / global_refs 详情

## Artifacts

- **Reads**：`versions/<v>/tasks/T-*.yaml`（task 定义）、`task execute` 返回的 context bundle（含 `impl_refs ∪ global_refs` 内容）。
- **Writes**：业务代码（由 AI 编辑工具直接落盘到具体业务路径）；`task complete` 触发 task YAML 的 `code_refs` 字段更新（CLI 写）。
- **严禁**：直接写 `.meta/`、`versions/`、`docs/global|prd|impl/`——所有 AIT 状态写入必须走 CLI。

## Workflow

1. 解析触发参数得到 `task_id`，调 `task execute <id>` 拿 bundle JSON。
2. 复述 `task_id`、`impl_refs` 列表、`global_refs` 列表给用户确认聚焦范围。
3. 按 task YAML 的 `steps` 字段顺序，使用 AI 编辑工具改业务代码；每完成一个 step 简要汇报。
4. 用户/AI 执行 `git add` + `git commit`（建议 commit message 格式：`feat(<task_id>): <heading>`）。
5. 拿到 commit hash 后调 `task complete <id> --commit <hash> --path <file1> --path <file2> ...` 收口。
6. 失败路径：调 `task fail <id>` 标记并把控制权移交 `ait-resume`（按返回的 `code` 走恢复链路）。

## Output Contract

每步必须复述：
- `task_id`
- 当前 step 序号 / 总数
- commit hash（步骤 5 之后）
- code_refs 路径列表（步骤 5 之后）

不要静默执行；不要原样 dump bundle 内容（仅摘要 impl_refs / global_refs 名称即可）。

## Common Pitfalls

| Code | Symptom | Recovery |
|---|---|---|
| `BLOCKED` | 依赖 task 未 done | 先跑 `depends_on` 列出的上游 task |
| `TASK_NOT_FOUND` | id 不存在或 task 路径迁移未生效 | 用 `task list --version <v>` 核对 id；必要时 `reindex` 刷新台账 |
| commit 缺失 | `git log` 空或用户漏跑 commit | 引导补 commit 后重试 `task complete` |
| `LOCKED`（impl/PRD 锁定后试图改 task）| 通常意味着规划阶段没跑全 | 接受 task 状态不可改；要改设计需 `version reset --confirm` |

## Boundaries

- 不嵌入具体业务代码模板（只编排流程，业务实现由 impl chunk 决定）。
- 不直接调用 `ait-resume`（失败时移交控制权由 AI 根据 `code` 自主切换）。
- 不写 `.meta/changes/*.yaml`（task complete 会自动追加）。
