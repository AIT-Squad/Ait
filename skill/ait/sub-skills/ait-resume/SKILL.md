---
name: ait-resume
description: INVOKE THIS SKILL when an AIT CLI command fails or the user asks how to resume an interrupted AIT workflow.
---

# ait-resume

## Purpose

根据 AIT CLI JSON 中的 `code` 与 `error` 字段，解释失败原因并给出最短恢复路径。

## CLI Dependencies

- `project-docs/.ait/ait-cli version status <version>`
- `project-docs/.ait/ait-cli prdv1 show <prd-file> [chunk-id]`
- `project-docs/.ait/ait-cli impl show <impl-chunk-id>`
- `project-docs/.ait/ait-cli context <chunk-id>`
- `project-docs/.ait/ait-cli state --format json`

## Artifacts

- **Reads**：CLI 错误 JSON、版本状态、chunk show/context 输出。
- **Writes**：不直接写文件。
- **Side-effect**：无。

## Workflow

1. 读取失败命令返回的 `code` 与 `error`。
2. 判断属于 root、PRD、impl、merge、state 或 graph 领域。
3. 如需补充信息，调用只读命令查看状态。
4. 输出恢复步骤，并给出下一条应执行的 `project-docs/.ait/ait-cli` 命令。

## Output Contract

必须包含：失败码、原因、恢复步骤、下一条命令。不要隐瞒 `ok=false`。

## Common Pitfalls

- `NOT_AT_PROJECT_ROOT`：切换到包含 `project-docs/` 的项目根。
- `CWD_INSIDE_PROJECT_DOCS`：退出 `project-docs/`。
- `PRD_NOT_COMMITTED`：先提交相关 PRD。
- `CHUNK_NOT_IN_VERSION`：确认 chunk 是否通过 CLI 注册。
- `MERGE_NO_COMMITTED`：先提交版本内 chunk。
- `COMMIT_EMPTY`：确认是否存在 staged chunk。