<!-- @id:prd-skills-overview -->
# 概述

## 背景

当前项目的 ait skill 是一个 **monolithic SKILL.md**（`skill/ait/SKILL.md`，216 行），把 PRD 三阶段讨论、impl 设计讨论、版本合并、reindex 等所有流程混合在一份文档中。这种组织方式在流程数量增长后会出现两个问题：

1. AI 加载单一 skill 时，prompt 上下文被无关流程稀释，触发关键词难以收敛
2. 单一文档难以承载"按角色/阶段触发不同行为"的协作模式

## 目标

引入参考项目（`/Users/jenningwang/PycharmProjects/version-design/`）的 **micro-skill 思想**：把流程沿"用户当前所处阶段"切分为多个独立 skill，每个 skill 只在其对应阶段被 INVOKE。**目标是扩充当前 ait skill 的能力，不是替换。**

## 取舍原则

| 原则 | 说明 |
|---|---|
| CLI 单源 | 子 skill 不引入新 CLI、不改动 init、不直接读写 `docs/` 或 `.meta/`，全部通过 `bin/ait` 现有命令操作 |
| 不引入 phase/task 体系 | 参考项目的 `.planning/phases/<phase>/` + `progress.json` + `issues.md` 暂不引入；本期 4 个 skill 全部围绕版本（vX.Y）+ chunk 三态机重构 |
| format 统一 | 参考项目 SKILL.md 中 `chunk-id` / `ait draft new` / `.planning/STATE.md` 等术语必须按当前项目术语对齐改写 |
| router 模式 | 主 SKILL.md 改造为 router：保留全局速查 + Common Pitfalls + Sub-skills 索引；具体流程下沉子 skill |

<!-- @id:prd-skills-rename-block-to-chunk -->
# Block 到 Chunk 的术语统一重构

## 背景

参考项目的版本管理单元称为 **chunk**，当前项目称为 **block**。两者语义完全相同。为了与 micro-skill 体系（其内部均使用 chunk 术语）对齐，本期把 `block` 在全项目重命名为 `chunk`。

## 重构范围

### 代码符号

| 当前 | 重构后 |
|---|---|
| `skill/ait/ait/block_parser.py` | `chunk_parser.py` |
| `BlockParser` 类 | `ChunkParser` |
| `parse_blocks()` / `serialize_blocks()` | `parse_chunks()` / `serialize_chunks()` |
| Schema 字段 `prd_blocks` / `impl_blocks` | `prd_chunks` / `impl_chunks` |
| 错误码 `BLOCK_NOT_IN_VERSION` | `CHUNK_NOT_IN_VERSION` |
| 错误码 `BLOCK_NOT_FOUND` | `CHUNK_NOT_FOUND` |
| `index_manager.py` 中所有 `block` 标识符 | `chunk` |

### 索引与元数据文件

| 当前 | 重构后 |
|---|---|
| `.meta/blocks-index.yaml` | `.meta/chunks-index.yaml` |
| `.meta/blocks-index-{vX.Y}.yaml` | `.meta/chunks-index-{vX.Y}.yaml` |
| YAML 内字段 `blocks:` | `chunks:` |

### 块标记语法（向后兼容）

- 新写入统一使用 `<!-- @id:prd-xxx -->`（不改为 `@chunk:`，保持简洁）
- 文档与代码注释中的"块"统一称为 "chunk"

### CLI 输出 JSON 字段

| 当前字段 | 重构后字段 |
|---|---|
| `block_count` | `chunk_count` |
| `block_ids` | `chunk_ids` |
| `block_id` | `chunk_id` |

### 用户态文档迁移

- 已存在的 `project-docs/docs/prd/*.md` 中 `<!-- @id:xxx -->` 注释保持不变（只是术语层重命名，不影响标记语法）
- 已存在的 `.meta/blocks-index.yaml` 在重构落地时自动迁移（开发 impl 阶段需提供一次性迁移脚本或在 reindex 时透明改名）

## 验收标准

- 全代码 `grep -ri 'block' skill/ait/ait/` 命中数 = 0（除注释中的英文单词 "block" 在自然语言含义下保留）
- 全文档 `grep -ri 'block' skill/ait/SKILL.md skill/ait/references/` 命中数 = 0（同上）
- 现有 PRD/impl 用例（`project-docs/docs/`）的 `bin/ait reindex` + `bin/ait prd show` 全部通过

<!-- @id:prd-skills-layout -->
# 嵌套目录布局

## 决议

所有子 skill 全部嵌套在 `skill/ait/sub-skills/<name>/` 下，不另起 `skill/ait-xxx/` 同级目录。理由：

1. 单一 skill 安装入口（`skill/ait/`）保持 init 工作流不变
2. 子 skill 与主 skill 共享同一 venv 与 `bin/ait`，免重复初始化
3. 用户在 IDE 加载主 skill 时，子 skill 自然可见

## 最终布局

```
skill/ait/                          ← 主 skill（router 角色，扩充能力的载体）
├── SKILL.md                        ← router：CLI 速查 + Common Pitfalls + Sub-skills 导航
├── README.md                       ← 不变
├── pyproject.toml                  ← 不变
├── bin/                            ← 不变（ait / ait.cmd）
├── ait/                            ← Python 包，全部 block→chunk 重构
├── references/                     ← 不变（block-system.md 等内部术语随之改名）
├── templates/                      ← 不变
└── sub-skills/                     ← 【新增】子 skill 集合
    ├── ait-discuss/SKILL.md        ← PRD 三阶段讨论
    ├── ait-impl-discuss/SKILL.md   ← impl 设计讨论
    ├── ait-progress/SKILL.md       ← 版本进度面板
    └── ait-resume/SKILL.md         ← 失败恢复
```

## 命名规则

- 子 skill 目录名：`ait-<verb>`（小写 + 连字符），与参考项目对齐
- 每个子 skill 必须包含且仅包含 `SKILL.md` 一个文件（与参考项目对齐）
- 子 skill 不允许引入额外的 `bin/`、`venv/`、`pyproject.toml` —— 共用主 skill 的运行时

<!-- @id:prd-skills-format-adapt -->
# 子 Skill 格式适配规范

## 参考项目与当前项目的格式差异

| 维度 | 参考项目 | 当前项目对齐项 |
|---|---|---|
| frontmatter | `name` + `description`（含 INVOKE 触发语） | 沿用，额外要求：`description` 必须以 `INVOKE THIS SKILL when ...` 起头（与主 SKILL.md 风格一致） |
| chunk 术语 | `chunk-id` / `chunk` | 沿用 chunk（重构后） |
| CLI 引用 | `ait list` / `ait scan` / `ait draft new` / `ait progress show` / `ait resume` | 全部替换为 `bin/ait <subcommand>` 当前等价命令（见映射表块） |
| artifacts 读取源 | `.planning/STATE.md` / `.planning/ait/progress.json` / `.planning/ait/issues.md` | 全部替换为 `.meta/versions/<vX.Y>.yaml` + `.meta/chunks-index.yaml` + `.meta/changes/`（无 `.planning/` 目录） |
| Decision Anchors 段 | 引用 DEC-501 ~ DEC-512 | 删除整段（当前项目无 DEC 编号体系） |
| ▶ Next Up 段 | 引用 `ait next-up <skill> --on success` | 改为静态文本，列出下一阶段子 skill（当前项目无 `ait next-up` CLI） |

## 强制契约

每个子 SKILL.md 必须满足：

1. frontmatter 触发语：`description` 字段以 `INVOKE THIS SKILL when ...` 起头
2. CLI Dependencies 表：列出本 skill 调用的所有 `bin/ait` 命令 + 触发时机 + 副作用
3. Artifacts 段：明确 Reads / Writes / Side-effect，写入路径仅限 `bin/ait` CLI 路径
4. 写入禁令：明确写入"绝不直接写 `docs/` 或 `.meta/`，必须通过 `bin/ait`"
5. Common Pitfalls 段（可选）：与主 SKILL.md 同名段落对齐，列出本 skill 特有错误码

## 输出契约

- 子 skill 调用 `bin/ait` 后获得 JSON：`{"ok": true/false, "data"/"error", "code"}`
- 子 skill 在对话中复述 `data` 关键字段（如 `req_id`、`chunk_count`、`file`），而非原样 dump JSON
- 失败时必须复述 `error` + `code`，让用户能直接对照 SKILL.md 的 Pitfalls 自助排错

<!-- @id:prd-skills-mapping -->
# 4 个 Skill 的迁移映射表

## ait-discuss

| 维度 | 参考项目 | 本期改造 |
|---|---|---|
| 职责 | adaptive PRD 讨论 + 写 ADD/MODIFY/DELETE draft | 不变（adaptive 三阶段：Clarify → Design → Generate） |
| `ait list` | 列出已有 chunk | → `bin/ait reindex` 后读 `.meta/chunks-index.yaml`（v0.2 引入 `bin/ait chunk list` 单独 PRD 处理） |
| `ait draft new --op ADD` | 产 ADD draft | → `bin/ait prd create "<title>"` + `bin/ait prd save-draft <req_id>` |
| `ait draft new --op MODIFY` | 产 MODIFY draft（带 base-hash） | → `bin/ait prd save-draft <req_id>`（覆盖，base_hash 由 confirm 阶段校验） |
| `ait draft confirm` + `ait draft merge` | confirmed → merged | → `bin/ait prd confirm <req_id> --file prd/<slug>` + `bin/ait prd commit prd/<slug> -m ...` |
| 删除策略 | DELETE draft | 本期不支持（当前 CLI 无 delete；写入 PRD non-goals） |
| 工作目录 | 任意 | 必须在 `project-docs/` 父目录 |

## ait-impl-discuss

| 维度 | 参考项目 | 本期改造 |
|---|---|---|
| 职责 | 为稳定的 PRD chunk 驱动 impl 设计 | 不变 |
| `ait context <prd-chunk> --depth 1` | 拉 PRD + 邻居作为 prompt 上下文 | → `bin/ait context <prd-chunk-id> --scenario prd-to-impl` |
| 落盘方式 | 直接写 `docs/impl/<stem>.md` + `ait scan` | → `bin/ait impl create <prd-chunk-id> --content-file <tmp>`（CLI 自动注入 `@ref ... rel:implements`） |
| 索引重建 | `ait scan` | → 由 `impl create` 自动 reindex；手工修文件后用 `bin/ait reindex` |
| commit | 不要求（参考项目 impl 解耦于 SemVer） | 要求走 `bin/ait impl commit <impl-chunk-id> -m ...`（PRD 必须先 committed） |

## ait-progress

参考项目依赖 `.planning/STATE.md` + `progress.json` + `issues.md`，当前项目全部不存在。本期改造为：

| 维度 | 参考项目 | 本期改造 |
|---|---|---|
| 数据源 | STATE.md + progress.json + issues.md | `.meta/versions/<vX.Y>.yaml` + `.meta/chunks-index-<vX.Y>.yaml` + `.meta/changes/` |
| CLI | `ait progress show` | 本期不引入新 CLI，子 skill 自己调用现有命令组合（占位实现）：`bin/ait reindex` 后读 `.meta/chunks-index-<vX.Y>.yaml` 统计 working/staged/committed 三态分布 |
| 渲染面板 | Phase / Milestone / Tasks{done,running,pending,failed} / Open issues | 改为 Version / Requirements / Chunks{working,staged,committed} / Pending merges（具体格式见 ait-progress 子 skill SKILL.md） |
| 长远规划 | （已实装） | 单独 PRD 引入 `bin/ait version status <vX.Y>` CLI 后，本 skill 改为 thin wrapper |

## ait-resume

参考项目依赖 `issues.md`，当前项目不存在。本期改造为：

| 维度 | 参考项目 | 本期改造 |
|---|---|---|
| 数据源 | `.planning/ait/issues.md`（结构化 ISS 条目） | CLI 错误码字典（`PRD_NOT_COMMITTED` / `MERGE_CONFLICT` / `CHUNK_NOT_IN_VERSION` / `ID_FORMAT` 等，已在 SKILL.md Common Pitfalls 列出） |
| CLI | `ait resume` | 本期不引入新 CLI，子 skill 通过：1) 询问用户上一次失败的 CLI 命令 + JSON 错误；2) 解析 `code` 字段；3) 在对话中给出恢复建议（建议命令 + 修复路径） |
| 触发时机 | 用户主动调用 / 失败后 ait-execute 自动 next | 仅用户主动 `/ait-resume` 调用（当前无 ait-execute） |
| 长远规划 | （已实装 issues.md） | 单独 PRD 引入 `.meta/issues.yaml` 与 `bin/ait resume` 后，本 skill 改为 thin wrapper |

<!-- @id:prd-skills-router -->
# 主 SKILL.md Router 改造

## 改造目标

把当前 `skill/ait/SKILL.md`（216 行）拆为：

- 保留在主 SKILL.md（router）：项目布局说明、CLI 速查表、Common Pitfalls、MVP Scope Boundaries、Sub-skills 索引
- 下沉到子 SKILL.md：PRD 三阶段讨论详细流程（`/ait prd <title>` 段）→ ait-discuss；impl 生成详细流程（`/ait impl <prd-chunk-id>` 段）→ ait-impl-discuss

## Router 必备段落（最终结构）

1. How This Skill Works（保留 + 新增 sub-skills 加载说明）
2. Project Layout（保留）
3. Commands 速查表（保留，但每条命令的"长流程说明"指向对应子 skill）
4. Sub-skills 索引（新增）：列出 4 个子 skill 的 Trigger / Purpose
5. Required Knowledge for Driving AIT（保留）
6. Common Pitfalls（保留 + 子 skill 特有 pitfall 仍写在子 skill 内不上浮）
7. MVP Scope Boundaries（保留 + 增补"sub-skills 不引入 phase/task"）

## 不变项

- frontmatter `name: ait` + `description` 不变
- bin/ait 入口与首次安装逻辑不变
- references/ 与 templates/ 内容不变（仅 block→chunk 术语改写）

<!-- @id:prd-skills-contract -->
# 子 Skill 写入与调用契约

## 工作目录约束

- 所有子 skill 在 INVOKE 时必须先验证 CWD 存在 `project-docs/` 子目录
- 若不满足，直接转交 `bin/ait` 的 `NOT_AT_PROJECT_ROOT` 错误码给用户，不在 skill 内重新实现校验
- 这与主 SKILL.md 现有约定一致

## 写入路径

| 写入对象 | 仅允许通过 |
|---|---|
| `docs/prd/*.md` | `bin/ait prd confirm` + `bin/ait version merge`（间接） |
| `docs/impl/*.md` | `bin/ait impl create` + `bin/ait version merge`（间接） |
| `versions/<vX.Y>/prd/*.md` | `bin/ait prd confirm` |
| `versions/<vX.Y>/impl/*.md` | `bin/ait impl create` |
| `.meta/**/*` | `bin/ait` 任意写命令的副产物（CLI 自动维护） |

禁令：子 skill 不得通过任何 IDE / shell 工具直接 `echo > file` 或 `edit_file` 这些路径。

## 错误处理

- 子 skill 接到 `{"ok": false, "error": "...", "code": "..."}` 时：
  1. 向用户复述 `error` 自然语言 + `code` 标识符
  2. 对照主 SKILL.md 的 Common Pitfalls 表，给出对应的修复命令
  3. 不重试隐藏错误（不允许 swallow），失败必须可见

## 自然语言

- 所有子 skill 的对话语言与当前用户偏好对齐：中文对话 + 中文代码注释（与项目现有偏好一致）
- frontmatter / 命令 / 错误码使用英文（与 CLI 输出对齐）

## 触发关键词

每个子 skill `description` 字段的 INVOKE 触发语必须：

- 以 `INVOKE THIS SKILL when ` 起头
- 明确触发场景（用户在哪个阶段说什么话时被加载）
- 不与其他子 skill 触发条件重叠（router 模式下重叠会导致 IDE 加载多个 skill 稀释 prompt）

<!-- @id:prd-skills-non-goals -->
# 非目标（本期不做）

| 非目标 | 留给后续 |
|---|---|
| 不迁移 ait-plan / ait-plan-check | 待 phase/task 体系引入后单独 PRD（参考 `todo.md` 需求 2 之后） |
| 不迁移 ait-build-tasks / ait-execute | 同上 |
| 不引入 `.planning/phases/` / `STATE.md` / `progress.json` / `issues.md` | 同上 |
| 不修改 init 流程（`skill/ait/bin/ait` 与 `root.py` 不动） | `todo.md` 需求 2 |
| 不修改 `project-docs/` 硬编码约束 | 不计划 |
| 不引入 `chunk delete` / `prd delete` CLI | v0.2+ |
| 不引入 specgraph / `links-index.yaml` 重构 | `todo.md` 需求 3 |
| 不引入 search / focus 类命令 | `todo.md` 需求 4 |
| 不引入新 CLI 命令（progress / resume / next-up / list 等） | 后续 PRD（本期 ait-progress / ait-resume 用现有 CLI 组合实现占位） |
