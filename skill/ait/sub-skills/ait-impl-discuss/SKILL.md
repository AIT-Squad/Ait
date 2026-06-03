---
name: ait-impl-discuss
description: INVOKE THIS SKILL when the user asks to design implementation modules for an existing committed PRD chunk via `/ait impl <prd-chunk-id>` (implementation design stage).
---

# ait-impl-discuss

## Purpose

根据 committed PRD chunk 组装 AI 上下文，生成实现设计 chunk，并通过 `project-docs/.ait/ait-cli impl create` 注册到当前版本。

## CLI Dependencies

- `project-docs/.ait/ait-cli context <prd-chunk-id> --scenario prd-to-impl`
- `project-docs/.ait/ait-cli context <prd-chunk-id> --focus`
- `project-docs/.ait/ait-cli context <prd-chunk-id> --deps`
- `project-docs/.ait/ait-cli impl create <prd-chunk-id> --content-file <file> --impl-file impl/<name>`
- `project-docs/.ait/ait-cli impl show <impl-chunk-id>`
- `project-docs/.ait/ait-cli impl commit <impl-chunk-id> -m <message>`

## Artifacts

- **Reads**：目标 PRD chunk、L2 相关 impl 示例、SpecGraph 依赖。
- **Writes**：只通过 `project-docs/.ait/ait-cli impl create` 写入版本 impl 文档。
- **Side-effect**：新增 impl chunk，并注入 `rel:implements` 引用。

## Workflow

1. 调用 `project-docs/.ait/ait-cli context <prd-chunk-id> --scenario prd-to-impl`。
2. 若上下文过大，改用 `--focus`；若需要依赖，使用 `--deps`。
3. 设计 impl chunk，ID 使用 `impl-<domain>-<name>`。
4. 按当前代码库风格写清交付物、文件路径、接口、数据结构、验收。
5. 调用 `project-docs/.ait/ait-cli impl create`，必要时显式传入 `--impl-file`。
6. 向用户汇报生成的文件与 chunk ID。
7. 若用户要求提交，调用 `project-docs/.ait/ait-cli impl commit`。

## Output Contract

成功时摘要 `version`、`file`、`chunk_ids`。失败时复述 `error` 与 `code`，并给出下一步恢复建议。

## Common Pitfalls

- `PRD_NOT_FOUND`：目标 PRD chunk 不在 baseline 或当前版本。
- `PRD_NOT_COMMITTED`：先提交 PRD 再提交 impl。
- `IMPL_NO_CHUNKS`：生成内容缺少 `<!-- @id:impl-... -->`。
- `CHUNK_NOT_IN_VERSION`：不要手写文件绕过 `impl create`。