---
name: ait-resume
description: INVOKE THIS SKILL when an AIT CLI command fails or the user asks how to resume an interrupted AIT workflow.
---

# ait-resume

## Purpose

根据 AIT CLI JSON 中的 `code` 与 `error` 字段，解释失败原因并给出最短恢复路径。

## CLI Dependencies

- `project-docs/.ait/ait-cli version status <version>` — 查版本 phase / 三态 / 锁位
- `project-docs/.ait/ait-cli state --format json` — 机器可读版本状态摘要
- `project-docs/.ait/ait-cli specgraph validate-new-model [--version <v>]` — 只读诊断图合法性与 `target_file` 唯一性
- `project-docs/.ait/ait-cli deps <chunk-id>` / `impact <chunk-id>` — 查 chunk 上下溯关系
- `project-docs/.ait/ait-cli search <query>` — 定位 chunk

## Artifacts

- **Reads**：CLI 错误 JSON、版本状态、specgraph 诊断与关系查询输出。
- **Writes**：不直接写文件。
- **Side-effect**：无。

## Workflow

1. 读取失败命令返回的 `code` 与 `error`。
2. 判断属于运行环境（root/cwd）、版本生命周期、层级相位门禁（prd/fsd/tdd confirm）、写时门禁（内容契约 / context token / 唯一性）、图不变式，还是 merge/revert 落盘领域。
3. 如需补充信息，调用上面的只读命令查看状态；不要为了诊断去改文档。
4. 输出恢复步骤，并给出下一条应执行的 `project-docs/.ait/ait-cli` 命令。

## Output Contract

必须包含：失败码、原因、恢复步骤、下一条命令。不要隐瞒 `ok=false`。

## Version Reset 指引

- 未合入版本不满意：`version revert <v> --confirm` 整版清空（物理删除，无局部撤销）。
- 已 merged 版本：`version revert <v>` 先不带 `--confirm` 跑一次，读回 `NEED_CONFIRM` 警告里将被回滚的双仓锚点与将被删除的后续版本，确认无误再加 `--confirm`。
- 层级返工不必整版退出：`prd revert` / `fsd revert` / `tdd revert` 把对应层从 confirm 解冻回 creating 相位。

## Common Pitfalls

运行环境：

- `NOT_AT_PROJECT_ROOT`：切换到包含 `project-docs/` 的项目根。
- `CWD_INSIDE_PROJECT_DOCS`：退出 `project-docs/`。
- `PROJECT_DOCS_MALFORMED`：补齐缺失目录后重试。
- `USAGE_ERROR`：命令/参数拼写错误。旧模型命令面已整体退役，调用即返回此码——改用主线 `prd` / `fsd` / `tdd` / `codegen` 命令。

版本生命周期：

- `NO_ACTIVE_VERSION`：先 `version create <v>` 再写文档。
- `ACTIVE_VERSION_EXISTS`：一次只允许一个开放版本，先 merge 或 revert 上一版。
- `NO_VERSION` / `VERSION_NOT_FOUND`：指定 `--version`，或先 `version create <v>`。
- `PRD_NOT_CONFIRMED` / `FSD_NOT_CONFIRMED` / `TDD_NOT_CONFIRMED`：自顶向下严格推进，先 confirm 上一层。
- `PRD_LAYER_CLOSED` / `PRD_LAYER_NOT_OPEN` / `FSD_LAYER_NOT_OPEN` / `TDD_LAYER_NOT_OPEN`：相位不匹配，用对应层的 `confirm` / `revert` 调整相位。
- `CHUNK_LOCKED`：chunk 已 commit 锁定，本版本内不可再改；需要改动走 `version revert <v> --confirm`。
- `COMMIT_EMPTY`：版本内没有可提交的 working chunk，先创建内容。

写时门禁（零落盘，修好后重跑同一命令）：

- `PRD_REQUIREMENT_CONTRACT_VIOLATION`：需求 chunk 补齐用户故事与 `#### 验收标准` 编号条目（根 chunk 不受此约束）。
- `CONTEXT_TOKEN_REQUIRED` / `CONTEXT_TOKEN_INVALID` / `CONTEXT_TOKEN_STALE` / `CONTEXT_TOKEN_CONFLICT`：先无内容调同名 create 重新取讨论背景与 `context_token`，用新令牌重跑。
- `CONTEXT_SKIP_NOT_ALLOWED`：该场景不允许 `--skip-context`，走 token 流程。
- `DUPLICATE_BASELINE_CHUNK`：`--content` 里塞了 baseline 已存在的 chunk；只保留真正新增的 chunk，或改用 `--action modify`。
- `MODIFY_RENAME_COLLISION` / `DUPLICATE_OVERRIDES_TARGET`：修 `--overrides` 后重试。
- `ROOT_CHUNK_REQUIRED`：`--content` 必须逐字带上根 chunk 自身正文。
- `TDD_TARGET_FILE_REQUIRED` / `DUPLICATE_TARGET_FILE`：TDD 必须声明 `target_file`，且全局唯一。
- `TARGET_FILE_SCOPE_ESCAPE`：`target_file` 越出受治理范围，改到范围内路径。
- `MARKDOWN_CONTAINS_RELATION`：正文零关系原则——关系只能随创建命令出生，从正文剥离。
- `INVALID_PROJECT_NAME` / `INVALID_FILE_NAME`：`--name` 只接受小写字母数字下划线短横；`--file` 只接受本 kind 目录内的相对路径。

关系与不变式：

- `INVARIANT_VIOLATION`：读 `violations` 明细定位（`ORPHAN_CHUNK` 孤儿 / `TRACE_BROKEN` 断链 / `SPEC_CYCLE` 成环 / `MISSING_ENDPOINT` 幽灵端点 / `TDD_MULTI_PARENT` 多父 / `PRD_FSD_LINK_NOT_UNIQUE` 派生不唯一），补边或补规格后重跑 `version confirm`。
- `INVALID_DERIVES` / `INVALID_DECOMPOSES_TYPES` / `INVALID_FSD_DECOMPOSES` / `INVALID_DETAILS` / `FSD_MIXED_CHILDREN`：关系端点类型不合法，按四关系规则改用正确的创建命令。
- `DEPENDS_ON_UNKNOWN_SIBLING` / `DEPENDS_ON_SELF` / `DEPENDS_ON_ROOT_CHUNK` / `DEPENDS_ON_CROSS_LEVEL` / `INVALID_DEPENDS_ON_TYPES`：`depends_on` 只能指向同父的兄弟 internal split。
- `UNCOVERED_ARTIFACT` / `TEST_SPLIT_UNCOVERED`：受治理范围内的制品缺 TDD 属主，补 TDD 后再 confirm。

落盘与收口：

- `MERGE_NO_COMMITTED`：先 `version commit <v>` 把 chunk 锁定为 committed。
- `ACCEPTANCE_FAILED`：验收命令未通过，修代码后 `acceptance run` 复跑。
- `MERGE_ROLLBACK` / `MERGE_CONFLICT` / `MERGE_PLAN_INVALID`：docs 与 `.meta` 已字节级回退，按 `error` 修复后重试 merge。
- `GIT_COMMIT_FAILED` / `HOST_COMMIT_FAILED`：已自动回滚；修 git 状态后重试。
- `REVERT_ANCHOR_INVALID` / `REVERT_PRECHECK_FAILED`：回滚锚点不可解析，报告用户该版本无法自动回滚，不要手工改 git。
- `REVERT_RECOVERY_PENDING`：回滚中途失败且补偿未完成，**停止后续命令**，把 `error` 里的待恢复项原样报给用户。
- `PUSH_NO_REMOTE` / `PUSH_NO_UPSTREAM` / `PUSH_FAILED`：先配好 remote/upstream 再 `push`。
