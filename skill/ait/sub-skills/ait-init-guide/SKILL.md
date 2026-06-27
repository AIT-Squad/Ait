---
name: ait-init-guide
description: INVOKE THIS SKILL when /ait init returns status=incomplete and the user needs to fill missing docs/global/* files interactively
---

# ait-init-guide — diff-fill the docs/global baseline interactively

## Trigger

- `/ait init` 返回 `status=incomplete`，CLI 提示需要补 global 文件
- 用户主动询问"global 还有哪些没补"/"项目接入 ait 需要做什么"
- 在已 init 过的项目上再次跑 `init`，CLI 进入差异补全分支

## CLI Dependencies

- `project-docs/.ait/ait-cli init --check` — 诊断模式：返回 `status` + `files` 字典，不写文件
- `project-docs/.ait/ait-cli init [--skip name1,name2]` — 实际补全；`--skip` 列出的文件写入 `user-skipped` 占位（后续不再提示）
- `project-docs/.ait/ait-cli reindex` — 兜底：写完 global 后若 `chunks-index.yaml` 仍缺新增 chunk，手动跑一次刷新

## Artifacts

- **Reads**：`docs/global/overview.md`、`tech-stack.md`、`ddl.md`、`schema.md`、`api.md`、`.meta/chunks-index.yaml`。
- **Writes**：**全部由 CLI 写**。Sub-skill 不直接操作 `docs/global/*`；用户拒绝的项通过 `init --skip <names>` 让 CLI 写 `user-skipped` 占位（含 `<!-- @id -->`，后续 `_classify_global_file` 视为 `present`，不会再触发补全）。
- **Side-effect**：刷新 `.meta/chunks-index.yaml` + `.meta/specgraph.yaml`。

## Workflow

1. **诊断**：调 `init --check`，解析 JSON 的 `data.files` 字典（5 项：`overview / tech-stack / ddl / schema / api`，值为 `present | skeleton | missing`）。
2. **筛选**：列出所有 status ≠ `present` 的文件名，向用户朗读：
   > "我准备补 `<filename>.md` （当前状态：missing/skeleton），要现在补么？回复 yes/no。"
3. **逐项征询**：用户同意 → 加入 `to_fill` 列表；用户拒绝 → 加入 `to_skip` 列表。
4. **一次性写入**：所有决策完毕后，调一次 `init --skip <to_skip 逗号拼接>`（CLI 会同时补 `to_fill` 项 + 写 `to_skip` 占位）。
5. **反馈**：解析返回 JSON 的 `created_files` / `skipped` / `files` 字段，输出 ASCII 汇总表给用户：
   ```
   ┌──────────────┬───────────┐
   │ file         │ result    │
   ├──────────────┼───────────┤
   │ tech-stack   │ created   │
   │ api          │ skipped   │
   │ ...          │ ...       │
   └──────────────┴───────────┘
   ```
6. **后续指引**：若 `status` 已变 `ready`，引导用户跑 `prdv1 create` 进入第一个版本；否则提示"还有 X 项待补，请稍后再跑 `/ait init`"。

## Output Contract

- 复述 `--check` 的 `status` 与每个文件的状态
- 列出用户每一项决策（同意/拒绝）
- 复述最终 `created_files` 与 `skipped` 列表
- 若 CLI 报错，原样转述 `error` + `code`

## Common Pitfalls

| 现象 | 处理 |
|---|---|
| `--check` 返回 `status=ready` | 无需补全，引导用户跑 `prdv1 create`。 |
| `--check` 返回 `status=fresh` | 这是全新项目，直接调 `init`（无 `--skip`）执行 full bootstrap，不走差异补全。 |
| `init` 之后 `chunks-index.yaml` 缺新增 chunk | 兜底跑 `reindex` 刷新。 |
| 用户拒绝某项后又改主意 | 把对应 `docs/global/<name>.md` 删掉再跑 `init`，CLI 会重新视为 missing 并补全。 |
| 用户跑 `init` 时漏了 `--skip` | CLI 会把所有 missing/skeleton 项一次性补全（无破坏，但用户失去拒绝机会）。下次想跳过某项需先删文件、再带 `--skip` 重跑。 |

## Boundaries

- 不直接写 `docs/global/*.md`（Global Contract：写入只能走 CLI）。
- 不内嵌交互式输入框；逐项征询完全靠 AI ↔ 用户对话。
- 不调用 `prdv1 commit` / `impl commit`（那是后续阶段，由 ait-discuss / ait-impl-discuss 负责）。
- 不实现"已 skipped 的文件用户后续手动补内容后自动重纳管"——只要文件含 `<!-- @id -->` CLI 即视为 present，已自然支持该场景。
