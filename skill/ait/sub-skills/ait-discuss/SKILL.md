---
name: ait-discuss
description: INVOKE THIS SKILL when the user asks to write or discuss a product requirement document with `/ait prd <title>` (PRD authoring stage).
---

# ait-discuss

## Purpose

驱动 PRD 的 Clarify → Design → Generate 三阶段讨论，并将结果通过 `project-docs/.ait/ait-cli prd` 命令保存为 AIT 管理的版本 PRD。

## CLI Dependencies

- `project-docs/.ait/ait-cli prd create <title>`
- `project-docs/.ait/ait-cli baseline-summary --scope prd --format yaml`
- `project-docs/.ait/ait-cli context <overrides>`
- `project-docs/.ait/ait-cli prd resolve-candidates --from-file <file>`
- `project-docs/.ait/ait-cli prd save-draft <req_id> --content-file <file>`
- `project-docs/.ait/ait-cli prd confirm <req_id> --file prd/<slug>`
- `project-docs/.ait/ait-cli prd show <prd-file> [chunk-id]`

## Artifacts

- **Reads**：用户需求、`project-docs/.meta/requirements/*.yaml`、PRD 草稿状态。
- **Writes**：只通过 `project-docs/.ait/ait-cli prd save-draft` 与 `project-docs/.ait/ait-cli prd confirm` 写入。
- **Side-effect**：版本目录中产生 `prd/*.md`，版本 index 注册 `working` chunk。

## Workflow

1. 确认当前目录是包含 `project-docs/` 的项目根。
2. 调用 `project-docs/.ait/ait-cli prd create <title>`，记录 `req_id` 与 `version`。
3. **Phase 0: scan-baseline**：在 Clarify/Design 前识别 add/modify 决议。
   - 调用 `project-docs/.ait/ait-cli baseline-summary --scope prd --format yaml` 获取 baseline PRD 的 `id + heading + summary` 列表。
   - 将“用户原始需求 + baseline 摘要列表”喂给 LLM，要求输出严格 YAML：`modify_candidates`、`delete_candidates`、`adds`。其中 `delete_candidates` 默认保持空，除非用户显式声明删除。
   - LLM 输入上限 **≤ 5 KB**。若摘要列表超限，按用户需求关键词匹配 `id/heading/summary`，只保留最相关的前 N 条，逐步缩小 N 直到总输入不超过 5 KB。
   - 对 `modify_candidates` 中 `confidence < 0.8` 的候选最多取 3 条，逐个调用 `project-docs/.ait/ait-cli context <overrides>` 拉取全文并让 LLM 二次精判；二次判断后要么提高/降低 confidence，要么降级为 `adds`。
   - 将最终 candidates 渲染为 Markdown 表格供用户确认，列为 `new_id` / `action` / `overrides` / `confidence` / `reason`。用户可把某条 `action` 改为 `add` 以拒绝 modify。
   - 将用户确认后的 YAML 写入临时文件，并调用 `project-docs/.ait/ait-cli prd resolve-candidates --from-file <file>` 落盘到 `versions/<v>/.candidates.yaml`。
4. Clarify：提出 2-4 个聚焦问题，补齐边界、用户、验收标准和非目标。
5. Design：给出 3-6 个 PRD chunk，chunk ID 使用 `prd-<domain>-<name>`；若 Phase 0 判定为 modify，保留对应 `new_id` 并确保后续 `save-draft` 能与 candidates 对齐。
6. Generate：生成完整 Markdown，所有业务语义位于 chunk 内。
7. 调用 `project-docs/.ait/ait-cli prd save-draft` 保存草稿；若已存在 `.candidates.yaml`，CLI 会把 `action` / `overrides` 同步进版本 chunks-index。
8. 调用 `project-docs/.ait/ait-cli prd confirm` materialize 到 `versions/<v>/prd/`。
9. 向用户汇报 `req_id`、`version`、文件路径和 chunk ID。

## Output Contract

只摘要 CLI JSON 的关键字段：`req_id`、`version`、`file`、`chunk_ids`。如果 `ok=false`，复述 `error` 与 `code`，不要伪造成功状态。

## Common Pitfalls

- `ID_FORMAT`：要求用户确认或改写 chunk ID。
- `CONFIRM_FAILED`：检查草稿是否为空、文件路径是否不含 `.md`。
- `NOT_AT_PROJECT_ROOT`：提示切回项目根。
- `CWD_INSIDE_PROJECT_DOCS`：提示退出 `project-docs/`。