<!-- @id:impl-skills-layout -->

# Skill 子目录布局实现

## 目标

为 v1.2 遗留的 `prd-skills-layout` 补齐实现规划，建立 `skill/ait/sub-skills/` 作为 micro-skill 的唯一承载目录。

## 文件结构

```text
skill/ait/
  SKILL.md
  sub-skills/
    ait-discuss/SKILL.md
    ait-impl-discuss/SKILL.md
    ait-progress/SKILL.md
    ait-resume/SKILL.md
```

## 实现要求

- 每个子目录只包含一个 `SKILL.md`，不放脚本、缓存或运行时产物。
- 子 skill 名称使用小写短横线，触发语必须互斥。
- 本 chunk 只负责目录和占位文件创建，具体行为由 `impl-skills-format-adapt` 与 `impl-skills-mapping` 补全。

## 验收

- `skill/ait/sub-skills/ait-*/SKILL.md` 共 4 个文件存在。
- 主 `SKILL.md` 能索引这些子 skill。

<!-- @ref:prd/backlog#prd-backlog-v12-legacy rel:implements -->

<!-- @id:impl-skills-router -->

# 主 SKILL.md Router 改造实现

## 目标

将主 `skill/ait/SKILL.md` 从完整流程文档改造成 router，只保留全局规则、命令速查、项目布局、子 skill 索引和错误处理边界。

## 保留内容

- AIT 项目布局与 `project-docs/` 工作根约束。
- `bin/ait` 命令速查与 JSON 输出契约。
- Common Pitfalls 与 MVP Scope Boundaries。
- `Sub-skills 索引`：列出 `ait-discuss`、`ait-impl-discuss`、`ait-progress`、`ait-resume` 的 Trigger 与 Purpose。

## 下沉内容

- PRD Clarify → Design → Generate 流程下沉到 `ait-discuss`。
- Impl context → generate → create 流程下沉到 `ait-impl-discuss`。
- 三态进度展示下沉到 `ait-progress`。
- 错误恢复建议下沉到 `ait-resume`。

## 验收

- `wc -l skill/ait/SKILL.md` 小于 120 行。
- `grep "Sub-skills 索引" skill/ait/SKILL.md` 有结果。

<!-- @ref:prd/backlog#prd-backlog-v12-legacy rel:implements -->

<!-- @id:impl-skills-format-adapt -->

# 子 Skill 格式适配实现

## 目标

为所有子 skill 的 `SKILL.md` 建立统一格式，确保参考项目迁移内容符合当前项目规范。

## 强制结构

每个子 skill 文档必须包含：

1. YAML frontmatter：`name` 与以 `INVOKE THIS SKILL when` 起头的 `description`。
2. Purpose：说明职责边界。
3. CLI Dependencies：列出会调用的 `bin/ait` 命令。
4. Artifacts：分 Reads、Writes、Side-effect 三类说明。
5. Workflow：用户触发后的分步行为。
6. Output Contract：只复述 JSON 中关键字段，不原样 dump。
7. Common Pitfalls：列出错误码与恢复建议。

## 写入规则

子 skill 不直接写 PRD/impl/版本文档；所有持久化必须通过 `bin/ait` CLI 完成。

## 验收

- 每个子 `SKILL.md` 均包含 `CLI Dependencies`、`Artifacts`、`Common Pitfalls`。
- frontmatter description 均以 `INVOKE THIS SKILL when` 起头。

<!-- @ref:prd/backlog#prd-backlog-v12-legacy rel:implements -->

<!-- @id:impl-skills-contract -->

# 子 Skill 调用与写入契约实现

## 目标

补齐 `prd-skills-contract` 的实现规划，确保子 skill 在工作目录、写入行为、错误处理和语言偏好上与主 AIT 契约一致。

## 工作目录约束

- 调用任何 `bin/ait` 前，必须确认当前目录包含 `project-docs/`。
- 如果位于 `project-docs/` 内部，应提示用户切换到项目根目录。
- 不自动 scaffold 缺失的项目结构。

## 写入约束

- PRD 写入只允许 `bin/ait prd save-draft` 与 `bin/ait prd confirm`。
- Impl 写入只允许 `bin/ait impl create`。
- Version merge 只允许 `bin/ait version merge`。
- state 写入只允许未来的 `bin/ait state --save`。

## 错误处理

- 所有 CLI 错误必须复述 `error` 与 `code`。
- 对 `PRD_NOT_COMMITTED`、`CHUNK_NOT_IN_VERSION`、`ID_FORMAT`、`MERGE_CONFLICT` 给出下一步恢复建议。

## 验收

- 子 skill 中不存在引导直接写版本文档的描述。
- Common Pitfalls 能覆盖主要错误码。

<!-- @ref:prd/backlog#prd-backlog-v12-legacy rel:implements -->

<!-- @id:impl-skills-mapping -->

# 四个子 Skill 行为映射实现

## 目标

将参考项目的讨论、实现讨论、进度查看和恢复建议能力，映射为当前项目的四个子 skill。

## ait-discuss

- 负责 `/ait prd <title>` 的三阶段讨论。
- 调用 `bin/ait prd create`、`save-draft`、`confirm`。
- 输出 req_id、version、chunk_ids 与目标文件。

## ait-impl-discuss

- 负责 `/ait impl <prd-chunk-id>` 的实现设计。
- 调用 `bin/ait context <prd-chunk-id> --scenario prd-to-impl`。
- 生成 `impl-*` chunk 后调用 `bin/ait impl create`。

## ait-progress

- 本期作为轻量进度面板。
- 读取 `.meta/versions/<v>.yaml` 与 `.meta/chunks-index-<v>.yaml`。
- 输出 PRD/impl 三态统计，不写入文件。

## ait-resume

- 本期作为错误恢复助手。
- 根据 CLI JSON 的 `code` 字段给出恢复步骤。
- 不依赖 `.planning/ait/issues.md`。

## 验收

- 四个子 skill 触发语不重叠。
- 每个子 skill 的 CLI 映射均指向当前项目 `bin/ait` 命令。

<!-- @ref:prd/backlog#prd-backlog-v12-legacy rel:implements -->

<!-- @id:impl-skills-overview -->

# Micro-skill 总览实现

## 目标

为 `prd-skills-overview` 补齐实现层说明，明确 v1.3 后 AIT skill 的组织原则：主 skill 负责路由，子 skill 负责具体流程。

## 设计原则

- 主入口轻量化：减少主 `SKILL.md` 的流程细节，降低上下文噪声。
- 子流程专业化：PRD、impl、progress、resume 各自独立维护。
- CLI 权威化：任何文档状态变更都通过 `bin/ait` 完成。
- 术语统一：全部使用 chunk，不恢复 block 术语。

## 验收

- 主 `SKILL.md` 中保留 `micro-skill` 或等价概述。
- 子 skill 索引能够说明每个子 skill 的职责边界。

<!-- @ref:prd/backlog#prd-backlog-v12-legacy rel:implements -->
