# Baseline PRD（merged baseline, edit by chunk only）

<!-- @id:prd-sections -->
## prd-sections

```python
@dataclass(frozen=True)
class PrdSections:
    overview: str        # 概述
    rules: list[str]     # 业务规则（拆 task 的依据）
    acceptance: list[str]# 验收标准（task 完成判定）
    boundary: str        # 边界与非目标
```

<!-- @id:prd-core-model -->
## 核心模型与版本原子性

### 概述
AIT 重构为围绕 **prd → impl → task** 三核心态的版本化 AI 开发流水线。每个版本是一个原子单元：要么完整走完确认链合并入全局，要么整体重置重来。该模型用"版本不可变"消除了局部回滚、增量继承、变更失效检测等复杂子系统。

### 业务规则
- 三核心态：PRD（需求意图）→ impl（实现设计）→ task（AI coding 执行单元），逐级派生
- 版本内不可变：任一 confirm 之后，对应内容在本版本内冻结，不可局部修改、撤销或回滚
- 唯一逃生口：`/ait version reset` 清空整个版本工作区，回到空白 PRD 状态重来
- 版本号：init 不算版本，首个功能版本从 v1.0 起，逐版递增
- 全程 chunk 聚焦：任何阶段只加载当前 chunk 及其关联，最小化 token
- 每个流程步骤都更新 `state.md`

### 验收标准
- [ ] prd/impl/task 三态数据结构与命令齐备
- [ ] confirm 后对应内容不可改（写保护生效）
- [ ] `version reset` 能清空版本工作区并回到起点（二次确认，物理删除）
- [ ] 每个命令执行后 state.md 被刷新

### 边界与非目标
- 不做局部回滚 / 单 chunk 放弃 / checksum 失效检测（被版本原子性取代）
- 不做增量版本继承（每版本独立）

<!-- @id:prd-init -->
## 项目初始化

### 概述
`/ait init` 是项目的一次性初始化入口，通过讨论生成项目的全局基线信息（全局 prd、impl 概览、global 静态/动态信息骨架），为后续版本开发建立上下文底座。

### 业务规则
- `/ait init` 启动讨论模式，引导生成：全局 PRD 概览、全局 impl 概览、global 信息（静态：技术栈/overview；动态：ddl/schema/api 骨架）
- init 产出写入 `docs/`（基线），不占用版本号
- init 为幂等保护：已初始化的项目再次 init 需提示确认
- init 完成后，项目进入"可开始版本开发"状态

### 验收标准
- [ ] `/ait init` 能讨论生成全局 prd/impl/global 并写入 docs/
- [ ] 生成的 global 区分 static 与 dynamic 两类
- [ ] 重复 init 有保护提示

### 边界与非目标
- init 不创建功能版本，不拆 task
- 动态 global 此阶段只建骨架，真实内容由后续 version confirm 从 impl 提取

<!-- @id:prd-prd-stage -->
## PRD 阶段

### 概述
版本开发的起点。通过创建或讨论确定本版本的 PRD，定稿后锁定。PRD 是本版本一切实现的需求源头。

### 业务规则
- `/ait prd create "title"`：带标题直接创建
- `/ait prd discuss`：启动讨论模式，讨论收敛后总结出 title
- title 写入 state.md 的独立字段（后续作为 git commit message）
- `/ait prd confirm`：确认 PRD 写入工作区并锁定；锁定后本版本任何流程不得以任何形式改动 PRD
- PRD chunk 采用四段固定结构（见 prd-formats）

### 验收标准
- [ ] create 与 discuss 两种入口都能产出 PRD chunk
- [ ] discuss 模式能总结 title 并写入 state.md 独立字段
- [ ] confirm 后 PRD 进入锁定态，再次修改被拒绝

### 边界与非目标
- 锁定后若需改 PRD，只能 `version reset` 整版重来，无局部解锁

<!-- @id:prd-impl-stage -->
## impl 阶段

### 概述
基于已锁定的 PRD chunk 设计具体实现。一个 PRD chunk 可对应多个 impl chunk（1:N）。impl 既是实现设计，又是动态 global（DDL/schema/api）的数据源。

### 业务规则
- `/ait impl create "chunk-id"`：为指定 PRD chunk 设计实现
- `/ait impl create`（无 id）：逐批交互，遍历待实现的 PRD chunk 依次设计
- 1:N 派生式命名：`impl-{源chunk}-{名}`（如 `impl-pet-archive-ddl`、`impl-pet-archive-api`）
- impl chunk 内用 `@extract` 注释标记可提取到动态 global 的片段（DDL/schema/api）
- impl 通过 `@ref ... rel:implements` 绑定其源 PRD chunk
- `/ait impl confirm "chunk-id"`：确认 impl 写入工作区并锁定；锁定后本版本不得改动 impl

### 验收标准
- [ ] 一个 PRD chunk 能派生多个 impl chunk
- [ ] 无 id 时逐批交互生成
- [ ] impl 中 `@extract` 标记的片段可被识别
- [ ] confirm 后 impl 锁定

### 边界与非目标
- 锁定后若需改 impl，只能 version reset 整版重来

<!-- @id:prd-task-stage -->
## task 阶段

### 概述
把锁定的 PRD+impl 拆分为 AI coding 任务（YAML 格式），并执行。一个 PRD chunk 可拆多个 task。execute 成功即自动收口，无需单独 confirm。

### 业务规则
- `/ait task create "chunk-id"`：为指定 PRD chunk 生成 task YAML；无 id 则逐批交互
- task 命名：`T-{源chunk}-NN`，文件 `T-{源chunk}-NN.yaml`
- task YAML 字段见 prd-formats，含 source_chunk/impl_refs/global_refs/depends_on/order_hint/steps
- `/ait task execute "taskId或chunk-id"`：AI coding 执行；无参则逐批交互
- task 状态机：created → executing → done / failed
- execute 成功自动标 done 并回写 code_refs（git commit hash + 文件路径）；失败停在 failed，可重跑
- 无 task confirm 步骤（execute 自动收口）

### 验收标准
- [ ] 一个 PRD chunk 能拆多个 task YAML
- [ ] execute 成功后 task 自动 done 且回写 code_refs
- [ ] execute 失败 task 停在 failed 且可重跑
- [ ] 依赖（depends_on）未满足的 task 不先执行

### 边界与非目标
- 不提供 task confirm；人工审核统一在 version confirm

<!-- @id:prd-version-merge -->
## 版本合并

### 概述

`/ait version confirm` 是版本的终点：守卫检查 -> 合并版本 prd/impl 到全局 -> 从 impl 提取动态 global -> 一次 git commit。采用两阶段+失败回退保证原子性。

v1.10 明确合并动作的边界：merge 只按版本索引中的 `action` 语义处理完整 chunk，不做语义 diff 或局部 patch。`modify` 是完整替换，`add` 只能新增 baseline 中不存在的 chunk，`delete` 删除指定 baseline chunk。任何把已存在 baseline chunk 作为 `add` 写入的情况都必须在 merge 前阻断，避免同 ID chunk 被追加到 baseline。

v1.11 明确 merge commit 的边界：`version confirm` 必须把最终 merged 状态文件一起纳入同一个 merge commit。confirm 返回成功后，git 工作区不得因为 `.meta/versions/<version>.yaml` 或 `versions/<version>/state.md` 的状态刷新而再次变脏，也不应要求用户再做第二个 “mark merged” commit。

### 业务规则

- 前置守卫：本版本所有 task 必须为 done，且 git 工作区干净；否则拦截并提示。
- 合并以 chunk 为维度：同名或 `overrides` 指向的 chunk 用本版本内容完整替换，其他 chunk 不动。
- `action=modify` 表示完整替换 `overrides` 指向的 baseline chunk。版本侧 markdown 中的该 chunk 必须已经包含最终希望保留的全部信息，merge 不从旧 chunk 自动搬运遗漏内容。
- `action=add` 只能用于 baseline 中不存在的新 chunk id。若 baseline 已存在同 ID chunk，merge 必须在写入前失败，错误码为 `DUPLICATE_BASELINE_CHUNK`，不得追加第二份同 ID chunk。
- `action=delete` 删除 `overrides` 指向的 baseline chunk。
- 继承来的 impl chunk 只用于当前版本的上下文、任务拆分和 impl 覆盖判断；不得作为 `add` 追加到 baseline。实现可以把 inherited chunk 表示为 no-op 记录，或表示为同 ID `modify` 替换，但最终 baseline 不得出现重复 chunk。
- 从本版本 impl 提取 `@extract` 标记的 DDL/schema/api 片段，按 chunk 合并进动态 global。
- 两阶段执行：1. 预检；2. merge 写入 docs/、baseline index/specgraph、snapshot 和最终 version/state 元数据；3. git commit（message = state.md 的 title）。
- `version confirm` 成功返回后必须没有未提交的状态尾巴；`phase: merged`、`merged_at`、`snapshot`、version index `status: merged`、`state.md` 中的 merged 展示都必须已经包含在同一个 merge commit 中。
- 失败回退：若 merge 或 git commit 失败，回退 merge（恢复 docs/ 到 merge 前），报错；要么全成要么全不动。

### 验收标准

- [ ] 有 task 非 done 时 version confirm 被拦截。
- [ ] 合并按 chunk 替换，不影响无关全局 chunk。
- [ ] `action=modify` 替换 `overrides` 指向的 baseline chunk，不追加同 ID chunk。
- [ ] `action=add` 且 baseline 已有同 ID chunk 时，merge 报 `DUPLICATE_BASELINE_CHUNK` 并且 baseline 不变。
- [ ] inherited impl chunk 在 version confirm 后不会向 baseline 追加重复 chunk。
- [ ] 动态 global 由 impl 的 @extract 片段提取生成。
- [ ] commit message 等于 title。
- [ ] commit 失败时 docs/ 回退到合并前状态。
- [ ] version confirm 成功后 git 工作区保持干净，不会留下 `.meta/versions/<version>.yaml` 或 `versions/<version>/state.md` 的二次提交。

### 边界与非目标

- 不在 version confirm 之外提供合并入口。
- 不做字段级、段落级或语义级 merge；modify 仍是 chunk 级完整替换。
- 不改变 task/PRD/impl 的提交前置要求；confirm 前仍要求用户把当前开发改动提交干净。
- 不引入系统级全局 `ait` 命令或 PATH 注入。

<!-- @id:prd-global -->
## 全局信息层

### 概述
global 承载跨版本的全局约束，分静态与动态两类，存于同一目录，靠 chunk 类型（category）区分。静态人工维护，动态由 version confirm 从 impl 提取。

### 业务规则
- 静态 global（category: static）：技术栈、overview 等，人工维护
- 动态 global（category: dynamic）：DDL、schema、api 等，由 version confirm 从 impl 的 @extract 片段提取
- 同目录存放：`docs/global/` 下不分子目录，靠 chunk id 前缀 + links-index 的 `category` 字段区分
- global chunk 参与 context 组装，任务执行时作为全局约束注入

### 验收标准
- [ ] links-index 中 global chunk 带 category: static|dynamic
- [ ] 静态 global 可人工编辑，动态 global 由提取生成
- [ ] task execute 时 global_refs 指向的约束被加载

### 边界与非目标
- 动态 global 不接受人工直接编辑（应改 impl 再 version confirm 提取）

<!-- @id:prd-formats -->
## 格式规范

### 概述
统一 PRD chunk、impl chunk、task YAML 的格式，沿用现有 `@id`/`@ref` HTML 注释体系，最小扩展。

### 业务规则
- PRD chunk 四段固定结构：`概述` / `业务规则` / `验收标准` / `边界与非目标`
- impl chunk 提取标记：`<!-- @extract:dynamic/{类型}#{chunk} -->` ... ```代码``` ... `<!-- @extract-end -->`，与 @id/@ref 同构，可覆盖代码块与纯文本
- task YAML 字段：`id` / `title` / `source_chunk` / `impl_refs` / `global_refs` / `depends_on` / `order_hint` / `steps` / `status` / `code_refs`
- 命名规范（派生式）：impl=`impl-{源chunk}-{名}`，task=`T-{源chunk}-NN`
- chunk id 沿用 `{type}-{domain}-{name}` 小写短横线规则，全局唯一

### 验收标准
- [ ] PRD chunk 解析器认四段结构
- [ ] impl 的 @extract 片段可被精确提取（边界正确）
- [ ] task YAML 字段完整且可被 execute 消费
- [ ] 派生式命名能反推源 chunk 血缘

### 边界与非目标
- 不引入 YAML frontmatter（保持 HTML 注释元数据哲学）
- 砍掉 v1.4 的 inherited_from / status_inherited / provenance 等增量继承字段

<!-- @id:prd-backlog-v12-legacy -->

# v1.2 遗留 PRD Chunk 实现清单

## 背景

v1.2 PRD 共规划了 8 个 PRD chunk，全部 committed。但 v1.2 的 impl 只实现了 2 个 impl chunk，仅覆盖了 `prd-skills-rename-block-to-chunk` 这一项。以下 6 个 PRD chunk **有 PRD 定义但无对应 impl**，构成 v1.3 的核心 backlog。

## 遗留 Chunk 清单（按优先级排序）

### 1. `prd-skills-overview` — 概述与目标

**PRD 位置**：`versions/v1.2/prd/skills.md` → `<!-- @id:prd-skills-overview -->`

**功能意图**：定义 micro-skill 拆分的背景、目标、取舍原则。是后续所有 skills 相关 impl 的顶层设计。

**impl 规划**：
- 新增 impl chunk：`impl-skills-overview`
- 内容：在主 `SKILL.md` 中保留 overview 段落；确认 router 模式下主 skill 的职责边界
- 验收：`grep -c "micro-skill" skill/ait/SKILL.md` > 0

**优先级**：高（所有 skills impl 的入口文档）

---

### 2. `prd-skills-layout` — 嵌套目录布局

**PRD 位置**：`versions/v1.2/prd/skills.md` → `<!-- @id:prd-skills-layout -->`

**功能意图**：定义 `sub-skills/` 目录布局、命名规则、每个子 skill 的文件约束（仅 `SKILL.md`）。

**impl 规划**：
- 新增 impl chunk：`impl-skills-layout`
- 内容：创建 `skill/ait/sub-skills/` 目录结构；创建 4 个占位 `SKILL.md`（ait-discuss / ait-impl-discuss / ait-progress / ait-resume）
- 验收：`ls skill/ait/sub-skills/ait-*/SKILL.md` 共 4 个文件存在

**优先级**：高（目录布局是后续所有子 skill 的前提）

---

### 3. `prd-skills-format-adapt` — 子 Skill 格式适配规范

**PRD 位置**：`versions/v1.2/prd/skills.md` → `<!-- @id:prd-skills-format-adapt -->`

**功能意图**：定义子 skill `SKILL.md` 的强制契约：frontmatter 触发语格式、CLI Dependencies 表、Artifacts 段、写入禁令、Common Pitfalls 段、输出契约。

**impl 规划**：
- 新增 impl chunk：`impl-skills-format-adapt`
- 内容：按 PRD 规范逐一填充 4 个子 skill 的 `SKILL.md` 内容（frontmatter、CLI Dependencies、Artifacts、Pitfalls）
- 验收：每个子 `SKILL.md` 包含 `INVOKE THIS SKILL when` 起头的 description；包含 CLI Dependencies 表；包含 Artifacts Reads/Writes/Side-effect 段

**优先级**：中（依赖 layout 先创建目录）

---

### 4. `prd-skills-mapping` — 4 个 Skill 的迁移映射表

**PRD 位置**：`versions/v1.2/prd/skills.md` → `<!-- @id:prd-skills-mapping -->`

**功能意图**：详细定义 ait-discuss / ait-impl-discuss / ait-progress / ait-resume 四个子 skill 的行为：职责、CLI 命令映射（参考项目 → 当前项目）、触发时机。

**impl 规划**：
- 新增 impl chunk：`impl-skills-mapping`
- 内容：按映射表逐一实现 4 个子 skill 的核心对话流程（三阶段讨论、context 组装、impl 创建、进度面板渲染、错误恢复建议）
- 验收：调用 `/ait-discuss` 能走完 Clarify→Design→Generate 三阶段；调用 `/ait-impl-discuss` 能为指定 PRD chunk 生成 impl draft

**优先级**：中（依赖 format-adapt 先定义契约）

---

### 5. `prd-skills-router` — 主 SKILL.md Router 改造

**PRD 位置**：`versions/v1.2/prd/skills.md` → `<!-- @id:prd-skills-router -->`

**功能意图**：把当前 216 行的主 `SKILL.md` 改造为 router：保留全局速查 + Common Pitfalls + Sub-skills 索引；具体流程下沉到子 skill。

**impl 规划**：
- 新增 impl chunk：`impl-skills-router`
- 内容：重构主 `SKILL.md`，抽出 PRD 三阶段讨论段到 ait-discuss；抽出 impl 设计讨论段到 ait-impl-discuss；新增 Sub-skills 索引段
- 验收：`wc -l skill/ait/SKILL.md` < 120 行（router 角色，不含具体流程）；`grep "Sub-skills 索引" skill/ait/SKILL.md` 存在

**优先级**：高（router 改造是子 skill 生效的前提）

---

### 6. `prd-skills-contract` — 子 Skill 写入与调用契约

**PRD 位置**：`versions/v1.2/prd/skills.md` → `<!-- @id:prd-skills-contract -->`

**功能意图**：定义子 skill 的工作目录约束、写入路径禁令（只能通过 `bin/ait` 写入）、错误处理规范、自然语言偏好、触发关键词约束。

**impl 规划**：
- 新增 impl chunk：`impl-skills-contract`
- 内容：在主 `SKILL.md` 的 Common Pitfalls 段补充子 skill 契约检查清单；在 4 个子 skill 的 Pitfalls 段各自补充特有错误码处理
- 验收：子 skill 在 INVOKE 时先检查 CWD 含 `project-docs/`；失败时必须复述 error + code

**优先级**：中（与 format-adapt 和 mapping 并行）

---

## 实现顺序建议

```
Phase 1（目录 + router）: prd-skills-layout → prd-skills-router
Phase 2（契约 + 格式）:   prd-skills-contract → prd-skills-format-adapt
Phase 3（行为实现）:    prd-skills-mapping → prd-skills-overview（文档补全）
```

## 验收总览

| PRD chunk | impl chunk | 状态 |
|---|---|---|
| `prd-skills-rename-block-to-chunk` | `impl-data-chunk-rename` + `impl-workflow-chunk-rename` | ✅ v1.2 已完成 |
| `prd-skills-overview` | `impl-skills-overview` | ⬜ v1.3 待实现 |
| `prd-skills-layout` | `impl-skills-layout` | ⬜ v1.3 待实现 |
| `prd-skills-format-adapt` | `impl-skills-format-adapt` | ⬜ v1.3 待实现 |
| `prd-skills-mapping` | `impl-skills-mapping` | ⬜ v1.3 待实现 |
| `prd-skills-router` | `impl-skills-router` | ⬜ v1.3 待实现 |
| `prd-skills-contract` | `impl-skills-contract` | ⬜ v1.3 待实现 |
| `prd-skills-non-goals` | N/A | ✅ 不需 impl |

<!-- @id:prd-block-format -->
## Block 标注格式

每个 Block 以 HTML 注释形式标注：

```markdown
<!-- @id:prd-book-entry -->
## 图书录入
...块内容...
```

标注规则：

1. 标注是独立一行，前后用空行分隔
2. `@id:` 后紧跟 Block ID，无空格
3. 标注行**属于 Block 内容的一部分**（不被排除），合并时保留
4. 一个标注只标识一个 Block，不允许嵌套

<!-- @id:prd-block-parse-rule -->
## 解析规则

Block 的边界由 `@id` 标注界定，不依赖标题层级：

| 规则 | 说明 |
|------|------|
| 起始 | `<!-- @id:xxx -->` 标注行 |
| 结束 | 下一个 `<!-- @id:yyy -->` 标注前一行，或文件末尾 |
| 内容 | 起始行至结束行的全部内容（含标注、标题、正文、代码块） |
| 文件头 | 第一个 `@id` 之前的内容归入"文件头"，合并时保留 |

详细解析算法见 [impl/block-parser.md](../impl/block-parser.md)。

<!-- @id:prd-block-id-naming -->
## ID 命名规范

格式：`{type}-{domain}-{name}`

| 段 | 取值 | 示例 |
|----|------|------|
| type | `prd` / `impl` | `prd` |
| domain | 子域名（小写短横线） | `block` / `version` / `workflow` |
| name | 语义化短名（小写短横线） | `format` / `lifecycle` |

完整示例：`prd-block-format`、`impl-version-manager-commit`。

约束：

1. ID 全局唯一（基线索引中不允许重复）
2. 同一版本索引中可有同 ID 多条记录（修订场景）
3. ID 一经 committed 不可重命名（已有 `@ref` 会失效）
4. ID 中只允许小写字母、数字、短横线

<!-- @id:prd-block-relations -->
## Block 关联（@ref）

跨 Block 引用通过专用注释建立：

```markdown
<!-- @ref:prd/book-management#prd-book-entry rel:implements -->
```

字段说明：

| 字段 | 说明 | 示例 |
|------|------|------|
| target | `{file}#{block-id}` | `prd/book-management#prd-book-entry` |
| rel | 关系类型 | `implements` |
| file | 相对于 `docs/` 的路径，无扩展名 | `prd/book-management` |

`@ref` 标注可放在两处：

1. 块内部任意位置（作为块内容的一部分）
2. 块的末尾（紧邻下一块前）

合并/解析时，`@ref` 与所在 Block 关联，写入 `links-index.yaml`。

<!-- @id:prd-block-relation-types -->
## 关系类型

内置 3 种：

| 关系 | 方向 | 语义 |
|------|------|------|
| `implements` | impl → prd | impl 块实现某个 PRD 块（最常见） |
| `modifies` | impl → impl | impl 块修改/取代已有 impl 块 |
| `see-also` | 任意 → 任意 | 补充参考（无强依赖） |

项目可在 `.meta/config.yaml` 的 `custom_relations` 中扩展。本项目扩展了：

| 关系 | 用途 |
|------|------|
| `refines` | impl 子块细化父块（如 algorithm refines api） |
| `depends-on` | impl 模块间依赖（如 version-manager depends-on index-manager） |

<!-- @id:prd-block-validation -->
## 块校验规则

所有 Block 必须满足（违反触发 E1 阻断，详见 [validation](validation.md)）：

1. ID 符合命名规范
2. ID 在基线索引中唯一
3. Block 内容非空（至少含标题）
4. `@ref` 的 target 必须可解析（E2 警告，不阻断）
5. `@ref` 的 rel 必须是内置或 `custom_relations` 中已声明的类型

<!-- @id:prd-index-baseline -->
## 基线索引

`docs/` 目录的全局 Block 索引存储在 `.meta/blocks-index.yaml`。

```yaml
version: 1
scope: global
updated: 2026-05-23T16:00:00+08:00
blocks:
  - id: prd-block-format
    file: prd/block-system
    heading: "Block 标注格式"
    level: 2
```

字段：

| 字段 | 必填 | 说明 |
|------|------|------|
| id | 是 | Block @id |
| file | 是 | 相对 `docs/`，无扩展名 |
| heading | 是 | 块标题文本（含 `#` 后内容） |
| level | 是 | 标题级别（2=##, 3=###, 1=# 作为文件标题不入索引） |

基线索引的特征：

1. ID 全局唯一
2. 扁平列表（无嵌套）
3. 只在 `/ait version merge` 时更新
4. 文件被手工编辑后，可用 `/ait reindex` 扫描 `docs/` 重建

<!-- @id:prd-index-version -->
## 版本增量索引

每个版本 `versions/{vX.Y}/` 拥有独立的增量索引 `.meta/blocks-index-{vX.Y}.yaml`。

与基线索引的差异：

| 维度 | 基线 | 版本 |
|------|------|------|
| 范围 | `docs/` | `versions/{vX.Y}/` |
| ID 唯一性 | 全局唯一 | 同 ID 可多条（修订场景） |
| 字段 | id/file/heading/level | + action / state / commit_id / overrides / amends / insert_after / base_hash / source_req |
| 更新频率 | merge 时 | stage/commit/edit 任何操作 |

完整 schema 见 [impl/version-manager.md](../impl/version-manager.md)。

<!-- @id:prd-index-record-fields -->
## 索引记录字段

基线索引仅 4 字段（见上）；版本索引扩展字段：

| 字段 | 适用 action | 说明 |
|------|-----------|------|
| `action` | all | `add` / `modify` / `delete` |
| `state` | all | `working` / `staged` / `committed` |
| `commit_id` | committed | 所属 commit |
| `overrides` | modify, delete | 覆盖的基线块 @id（冗余但明确） |
| `amends` | 修订 committed | 修订的 commit/block 标识 |
| `insert_after` | add | 插入位置的基线块 @id；null=末尾 |
| `base_hash` | modify, delete | 操作时基线块的哈希（冲突检测） |
| `source_req` | all | 来源需求 ID（追溯用） |

字段适用矩阵详见 [impl/version-manager.md](../impl/version-manager.md)。

<!-- @id:prd-index-isolation -->
## 分层隔离

基线索引与版本索引完全隔离：

1. 基线索引覆盖 `docs/`，版本索引覆盖 `versions/{vX.Y}/`，互不干扰
2. 版本只能从基线 fork（继承基线的 ID 命名空间）
3. 版本之间互不可见（V1.1 不能引用 V1.2 的 block）
4. 合并是单向操作：版本 → 基线，不存在"基线 → 版本"

<!-- @id:prd-index-links -->
## 引用索引

所有 `@ref` 关系汇总到 `.meta/links-index.yaml`：

```yaml
version: 1
updated: 2026-05-23T16:00:00+08:00
links:
  - from: impl/block-parser#impl-block-parser-api
    to: prd/block-system#prd-block-parse-rule
    rel: implements
```

links-index 是只读派生数据，由 block_parser 扫描所有 `@ref` 后生成。

用途：

1. AI 上下文组装的 L2 关联层（参见 [ai-context.md](ai-context.md)）
2. 影响面分析：修改 PRD 块时找出受影响的 impl 块
3. 一致性校验：检测悬空引用（target 不存在）

<!-- @id:prd-index-atomicity -->
## 原子性

索引写入采用 temp→rename 原子操作（POSIX 保证）：

1. 先写 `.meta/blocks-index.yaml.tmp`
2. fsync 后 rename 为 `blocks-index.yaml`
3. rename 失败时清理 tmp 文件

避免写入中断导致索引半残。Windows 平台用 `os.replace` 保证原子性。

<!-- @id:prd-scope-non-goals -->

# v1.3 非目标（Non-Goals）

## 原则

本文件列出 **v1.3 明确不做** 的事情，防止需求蔓延（scope creep），确保版本边界清晰。

---

## Non-Goal 1：不引入 `phases/` + `task/` 体系

**说明**：v1.2 `prd-skills-non-goals` 已明确不引入 `phases/` + `task/` 体系。v1.3 **继承该决策**。

**原因**：
- v1.3 的核心目标是 **v1.2 欠债清零 + todo.md 全量落地**
- `phases/` + `task/` 是更上层的项目管理概念，引入会显著扩大 scope
- 留到 v1.4+ 单独规划

**v1.3 的替代方案**：
- 用 **SpecGraph 的 `depends_on` 关系** 来表达 chunk 之间的依赖，不需要 phases 概念
- 用 **state.md 的健康度评分** 来追踪版本完成度，不需要 task 体系

---

## Non-Goal 2：不修改 `bin/ait` CLI 的主入口和参数解析

**说明**：v1.2 `prd-skills-non-goals` 已明确不修改 `skill/ait/bin/ait` 和 `root.py`。v1.3 **继承该决策**。

**例外（v1.3 允许的最小改动）**：

| 改动 | 是否允许 | 说明 |
|---|---|---|
| 新增 `ait/specgraph.py` + `bin/ait specgraph` 子命令 | ✅ 允许 | 新功能，不改动现有命令 |
| 新增 `ait/search.py` + `bin/ait search` 子命令 | ✅ 允许 | 同上 |
| 新增 `ait/context.py` 的 `--focus` / `--deps` 参数 | ✅ 允许 | 增强现有命令，不改动接口风格 |
| 新增 `ait/state.py` + `bin/ait state` 子命令 | ✅ 允许 | 新功能 |
| 修改 `root.py` 的 `init()` 函数内部逻辑 | ⚠️ 条件允许 | 仅通过 AI_HINT 注释触发子 skill，不改签名 |
| 修改 `bin/ait` 的参数解析（`argparse` 部分） | ❌ 不允许 | 违反 v1.2 non-goal |
| 修改现有子命令的 CLI 接口（参数 / 输出格式） | ❌ 不允许 | 向后兼容要求 |

---

## Non-Goal 3：不迁移参考项目中与当前项目规范冲突的功能

**说明**：`todo.md` 需求1 要求"按照当前项目的规范来重新组织 skills"。

**具体排除项**：

| 参考项目功能 | 排除原因 |
|---|---|
| `ait init` 增强逻辑（参考项目版本） | 当前项目 `init` 流程不动（`todo.md` 需求2 约束） |
| `.planning/STATE.md` 格式 | 当前项目用 `.meta/versions/<v>.yaml` + `.meta/chunks-index.yaml` |
| `.planning/ait/progress.json` | 同上，用 chunks-index 代替 |
| `.planning/ait/issues.md` | v1.2 non-goal，留 v1.4+ |
| `ait next-up` / `ait build-tasks` / `ait execute` | 需要 `phases/` + `task/` 体系，v1.3 不引入 |
| 参考项目的 `block` 术语 | v1.2 已完成 block→chunk 重构，统一用 `chunk` |

---

## Non-Goal 4：不实现语义搜索（Embedding + Vector Store）

**说明**：`prd-search-cli` 中规划了 `bin/ait search` 命令，但 **v1.3 只实现关键词搜索**。

**语义搜索留到 v1.4+**：
- 需要引入 embedding API（OpenAI / 本地模型）
- 需要向量数据库（Chroma / FAISS）
- 需要持久化索引（`.meta/search-index/`）
- 属于"高级功能"，不是 v1.3 的核心目标

**v1.3 的替代方案**：
- `bin/ait search` 支持正则表达式（`--regexp`）
- `bin/ait search --field <field>` 支持按 YAML frontmatter 字段过滤

---

## Non-Goal 5：不实现 SpecGraph 的高级查询（Mermaid 渲染 / Web UI）

**说明**：`prd-specgraph-index` 中规划了 SpecGraph 数据模型和 CLI 命令。

**v1.3 不做的高级功能**：

| 功能 | 留到 |
|---|---|
| 在 AI 对话中自动渲染依赖图（Mermaid） | v1.4+ |
| SpecGraph 的 Web UI 可视化（D3.js / ECharts） | v1.4+ |
| 跨版本 dependency conflict 检测 | v1.4+ |
| SpecGraph 的实时协作编辑 | 不在 roadmap 中 |

**v1.3 的替代方案**：
- `bin/ait specgraph export --format dot` 导出 Graphviz DOT（可用 `dot` 命令行渲染为 PNG）
- state.md 中用 ASCII 表格展示依赖关系

---

## Non-Goal 6：不修改 v1.2 已 committed 的 impl chunk

**说明**：v1.2 已 committed 的 2 个 impl chunk（`impl-data-chunk-rename` + `impl-workflow-chunk-rename`）**在 v1.3 中不动**。

**原因**：
- 这两个 impl chunk 已经 merge 到 baseline，属于 v1.2 的交付物
- v1.3 基于 v1.2 baseline 创建，不需要重新实现
- 如果这两个 impl 有问题，应该走 **hotfix 流程**（v1.2.1），而不是在 v1.3 中修改

**v1.3 的隐含契约**：
- `bin/ait version create v1.3 --based-on v1.2` 时，v1.2 的 2 个 impl chunk 自动继承
- v1.3 的 PRD chunk 可以引用这两个 impl chunk 作为前置依赖

---

## Non-Goal 7：不引入多版本并行开发支持

**说明**：v1.3 **不支持** 同时基于 v1.2 创建 v1.3 和 v1.4 并行的场景。

**当前限制**：
- `bin/ait version create <v>` 只支持基于单个 baseline 版本
- 不支持 `v1.4 based-on v1.2` 和 `v1.3 based-on v1.2` 同时存在时的 merge 冲突解决策略
- 不支持跨版本 chunk 复用（同一个 PRD chunk 被多个版本引用）

**留到 v1.4+**：
- 多版本并行开发的 merge 策略
- 跨版本 chunk 引用解析
- 版本分支的可视化（Git 风格）

---

## 总结：v1.3 Scope 边界

```
✅ 包含（In Scope）:
  - v1.2 遗留 6 个 PRD chunk 的 impl 规划 + 实现
  - todo.md 全部 4 个需求的 PRD 规划 + impl 实现
  - ait-state skill（驱动 state.md 生成）
  - SpecGraph 数据模型 + 基础 CLI
  - 检索/聚焦读取命令行（关键词模式）

❌ 不包含（Out of Scope）:
  - phases / task 体系
  - 语义搜索（embedding）
  - SpecGraph 高级可视化（Mermaid / Web UI）
  - 修改 v1.2 已 committed 的 impl
  - 多版本并行开发
  - 参考项目中与当前项目规范冲突的功能
```

<!-- @id:prd-overview-mission -->
## 使命

AIT（AI-Assisted Document Versioning System）让 AI 参与的 vibe coding 文档写作具备结构化的版本控制能力。

核心矛盾：传统 Git 以"文件"为版本控制单元，AI 生成的 markdown 文档需要更细颗粒度的"块级"管理；AI 协作过程中产生的需求讨论、PRD 草稿、impl 设计、代码生成需要全程可追溯、可回滚、可上下文复用。

AIT 提供以 `<!-- @id:xxx -->` 为锚点的 Block 版本控制，支持从需求到代码的全链路结构化管理。

<!-- @id:prd-overview-target-users -->
## 目标用户

| 角色 | 使用场景 |
|------|---------|
| AI 协作开发者 | 在 AI IDE（Claude Code / Cursor / Continue 等）中用 AIT 命令驱动 PRD→impl→code 流程 |
| 文档工程师 | 维护大型 PRD/设计文档的版本与依赖关系 |
| 团队 Tech Lead | 通过 impl 块跟踪关键技术决策的实现状态 |
| 开源项目维护者 | 让 AI 贡献者按结构化流程提交文档变更 |

<!-- @id:prd-overview-scope -->
## MVP 范围

MVP 覆盖 **单机** 模式下的核心闭环：

```
/ait prd <title>          → AI 三阶段讨论 PRD → 写入版本工作区
/ait prd commit           → 提交 PRD 到 committed
/ait impl <block-id>      → AI 基于 PRD 生成 impl
/ait impl commit          → 提交 impl
/ait version merge        → 合并到基线 docs/
```

MVP 不包含：代码生成、反向同步、多人协作、AI 改 block、IDE 跳转编辑、list、reindex。

<!-- @id:prd-overview-roadmap -->
## 路线图

| 版本 | 范围 | 状态 |
|------|------|------|
| V1（MVP） | 7 个核心命令 + 单机闭环 + Claude Code Skill 形态 | 开发中 |
| V1.1 | `list`/`edit`/`reindex` + 跨 AI IDE 适配（Cursor / Continue / Cline） | 规划 |
| V2 | 多人协作（基于 Git）+ `/ait impl code` 代码生成 + sync-status 双向同步 | 规划 |

每个版本结束以"合入基线"为分界。

<!-- @id:prd-overview-terminology -->
## 核心术语

| 术语 | 定义 |
|------|------|
| Block | 由 `<!-- @id:xxx -->` 标注的最小版本控制单元 |
| 基线（baseline） | `docs/` 目录，所有版本合并后的真实状态 |
| 版本（version） | `versions/{vX.Y}/` 下的增量工作区 |
| 三阶段 | working → staged → committed |
| @ref | 跨 Block 引用，形如 `<!-- @ref:<file>#<chunk-id> rel:<type> -->` |
| L1~L4 | AI 上下文的四层模型 |
| Skill | Claude Code 等 AI IDE 的可加载能力包，包含 SKILL.md + 脚本 |

<!-- @id:prd-overview-design-principles -->
## 设计原则

1. **内容与元数据分离**：markdown 只放内容 + `@id`/`@ref`，所有状态/版本信息在 `.meta/` 的 YAML 中
2. **块级原子**：合并的最小单位是块，不做行级 diff
3. **AI 友好**：所有命令的输出是结构化 JSON，便于 AI 消费；所有命令的设计避开"魔法"，让 AI 能准确预测系统行为
4. **跨 IDE 中立**：核心是纯 CLI（Python），各 AI IDE 通过自己的 Skill/Rule 机制包装
5. **可追溯**：每次 commit 产生 `chg-{id}.yaml`，合并产生快照，任何变更都能回到时间点

<!-- @id:prd-release-v13-overview -->

# v1.3 版本概述

## 背景

v1.2 完成了 PRD 规划（8 个 PRD chunk 全部 committed），但 **impl 实现严重滞后**：

| v1.2 PRD chunk | 是否有对应 impl | impl 状态 |
|---|---|---|
| `prd-skills-rename-block-to-chunk` | ✅ `impl-data-chunk-rename` + `impl-workflow-chunk-rename` | committed |
| `prd-skills-overview` | ❌ 无 | — |
| `prd-skills-layout` | ❌ 无 | — |
| `prd-skills-format-adapt` | ❌ 无 | — |
| `prd-skills-mapping` | ❌ 无 | — |
| `prd-skills-router` | ❌ 无 | — |
| `prd-skills-contract` | ❌ 无 | — |
| `prd-skills-non-goals` | N/A（非目标，不需 impl） | — |

**结论**：v1.2 有 **6 个 PRD chunk 未实现 impl**，需要在 v1.3 中补全。

## 三大目标

### 目标 1：v1.2 欠债清零
将 v1.2 中已 committed 但未实现 impl 的 6 个 PRD chunk，逐一规划并实现 impl chunk，确保 v1.2 PRD 的功能意图完整落地。

### 目标 2：todo.md 需求全量落地
实现 `todo.md` 中列出的 4 个需求：
1. 参考项目 skill 功能迁移（按当前项目规范重新组织）
2. init 流程智能识别旧项目
3. links-index.yaml 重构为 specgraph 格式
4. 检索/聚焦读取命令行迁移

### 目标 3：引入 state.md 版本进度面板
在每个 version 目录下新增 `state.md`，由 **ait-state skill** 在 `version merge` 之后驱动生成，记录版本完成进度、chunk 三态分布、需求映射关系，支持 AI 和用户快速了解版本健康度。

## 与 v1.2 的关系

- v1.3 **基于 v1.2 创建**（`bin/ait version create v1.3 --based-on v1.2`）
- v1.3 不是全新版本，而是 v1.2 的 **功能补全 + todo 需求追加**
- v1.2 已 committed 的 8 个 PRD chunk 全部继承到 v1.3，不需要重新讨论
- v1.3 新增的 PRD chunk 仅来自 `todo.md` 的 4 个需求 + `prd-skill-state`

## 版本边界

| 包含 | 不包含 |
|---|---|
| v1.2 遗留 6 个 PRD chunk 的 impl 规划 | v1.2 已实现的 2 个 impl chunk（已 committed，不动） |
| todo.md 全部 4 个需求的 PRD + impl | 新的 phase/task 体系（留 v1.4+） |
| ait-state skill（驱动 state.md 生成） | ait-progress / ait-resume 等其它子 skill 的实现（v1.2 non-goals，留后） |
| specgraph 引入（links-index.yaml 重构） | specgraph 的高级查询能力（留后） |

<!-- @id:prd-project-docs-only-overview -->
## 概述

**背景**：当前 AIT CLI 在任意 CWD 下都会启动——如果该目录已具备 `docs/` + `.meta/` 布局就直接接管，否则按提示 scaffold 出一份新的。这导致两类风险：

1. **目录歧义**：同一仓库里可以存在多份 AIT-managed 目录（如本仓库的 `project-demo/` 与 `project-docs/`），CLI 是否"对该项目生效"完全取决于 CWD，使用者难以一眼判断当前命令作用于哪一份元数据。
2. **误 scaffold**：在错误的目录下执行 `/ait prd` 之类的命令会无声地 scaffold 出一份空的 AIT 项目，污染目录结构。

**目标**：把 AIT 的"项目根"语义收紧到唯一约定——`<CWD>/project-docs/`，并在不满足时立即拒绝执行，不再 scaffold、不再自动推断。

**非范围声明**：本需求只调整 root 解析行为，不改变 PRD/impl/版本/合并等业务规则。已有的 `project-demo/` 不在治理范围内（仅作样例保留）。

<!-- @id:prd-project-docs-only-rules -->
## 业务规则

| 编号 | 规则 |
|---|---|
| R1 | 唯一合法的 AIT 工作根 = `<CWD>/project-docs/`（CWD 的直接子目录，名称严格匹配） |
| R2 | 目录名 `project-docs` **硬编**，不读取任何配置项、环境变量、CLI flag 来改名 |
| R3 | 不向上递归查找项目根 marker（`.git`、`pyproject.toml`、`.ait-root` 等一概不参与判定） |
| R4 | 不提供 `--root` / `-C` / `AIT_ROOT` 之类的覆盖入口 |
| R5 | `project-docs/` 内必须同时存在 `docs/` 和 `.meta/` 子目录才被视为合法工作根 |
| R6 | 一次命令执行内 root 解析结果**锁定**：命令运行期间不重新探测、不切换 |

<!-- @id:prd-project-docs-only-detection -->
## 目录定位

**触发时机**：所有 `bin/ait` 子命令（`prd`、`impl`、`version`、`reindex`、`context`）在解析子命令参数之前、加载任何元数据之前，先调用统一的 root 解析逻辑。

**算法**：

```
1. cwd ← os.getcwd()
2. candidate ← cwd / "project-docs"
3. 若 candidate 不是已存在的目录 → 抛 NOT_AT_PROJECT_ROOT（见错误场景 E1）
4. 若 (candidate / "docs") 或 (candidate / ".meta") 不是已存在的目录 → 抛 PROJECT_DOCS_MALFORMED（E2）
5. 若 cwd 本身位于 candidate 内部（即 cwd == candidate 或 cwd 是 candidate 的后代）→ 抛 CWD_INSIDE_PROJECT_DOCS（E3）
6. 否则 root ← candidate，写入命令上下文，后续路径解析全部基于 root
```

**不变量**：

- 解析完成后，CLI 内部不再使用 `os.getcwd()`，全部以解析得到的 root 为基准。
- 同一进程生命周期内 root 不变。
- 任何相对路径（`docs/prd/...`、`.meta/blocks-index.yaml`、`versions/v1.0/...`）都相对 root 解析。

<!-- @id:prd-project-docs-only-errors -->
## 错误场景

所有错误遵循统一的 JSON 输出契约：`{"ok": false, "error": "<人类可读>", "code": "<机器码>"}`，并以 exit code 1 退出。

| 编号 | code | 触发条件 | 提示文案（中文） |
|---|---|---|---|
| E1 | `NOT_AT_PROJECT_ROOT` | CWD 下没有 `project-docs/` 子目录 | 当前目录不是 AIT 项目根。请 cd 到包含 `project-docs/` 子目录的项目根目录后重试。 |
| E2 | `PROJECT_DOCS_MALFORMED` | `project-docs/` 存在，但缺 `docs/` 或 `.meta/` | `project-docs/` 结构不完整：缺少 `docs/` 或 `.meta/`。请检查目录或重新初始化。 |
| E3 | `CWD_INSIDE_PROJECT_DOCS` | CWD 本身就是 `project-docs/` 或其后代 | 请退出 `project-docs/`，从其父目录（项目根）运行命令。 |

**辅助信息**：错误 JSON 的 `data` 字段允许携带诊断信息（如解析过的 CWD 绝对路径、缺失的子目录名），便于排障，但 `code` + `error` 两个字段是稳定 API。

<!-- @id:prd-project-docs-only-non-goals -->
## 非目标

明确**不做**的事项，避免范围蔓延：

- ❌ 不实现 `--root` / `-C` / `AIT_ROOT` 等任何覆盖入口
- ❌ 不支持自定义目录名（`docs/`、`site/`、`project_docs` 一律不接受）
- ❌ 不向上递归查找项目根 marker（`.git`、`pyproject.toml`、`.ait-root` 等不参与判定）
- ❌ 不为 `project-demo/` 提供兼容性 shim——它仅作演示样例保留，本需求生效后将不再被 CLI 视为合法工作根
- ❌ 不处理 multi-root 工作区场景（一个项目内放多套独立 AIT 元数据）
- ❌ 不引入 scaffold 行为变化以外的命令语义改动；仅在 root 解析失败时拒绝执行

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
| `ait draft confirm` + `ait draft merge` | confirmed → merged | → `bin/ait prd confirm <req_id> --file <slug>` + `bin/ait prd commit prd/<slug> -m ...` |
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

<!-- @id:prd-skill-state -->

# 目标3：ait-state Skill（版本进度面板）

## 需求来源

用户明确要求：

> 有一个版本的完成进度和信息汇总，放到版本下，命名为 state.md
> state.md 由 skill 在 merge 之后驱动生成，做完 impl 之后 merged，然后确认后再生成 state.md
> state.md 在版本生成时候就产生，然后给用户显示当前的状态，包括 prd 规划进度，impl 规划进度，task 拆分后开发的进度

## 核心设计

### state.md 的生命周期

```
version create v1.3
      │
      ▼
【生成】state.md 初始版本（仅含版本元信息 + PRD 规划进度 0%）
      │
      ▼
... PRD chunks 逐条 prd save-draft → prd commit ...
      │
      ▼
【刷新】ait-state skill 被调用 → 更新 PRD 规划进度
      │
      ▼
... impl chunks 逐条 impl create → impl commit ...
      │
      ▼
【刷新】ait-state skill 被调用 → 更新 impl 规划进度
      │
      ▼
... （未来 v1.4+）task 拆分 → 开发进度 ...
      │
      ▼
【刷新】ait-state skill 被调用 → 更新开发进度
      │
      ▼
version merge v1.3
      │
      ▼
【最终刷新】ait-state skill 被调用 → 生成最终 state.md（含完整进度汇总）
```

### state.md 的三阶段内容

| 阶段 | 内容 | 数据来源 |
|---|---|---|
| Phase 1：PRD 规划中 | 版本元信息 + PRD chunk 三态分布（working/staged/committed）+ PRD 完成百分比 | `.meta/versions/<v>.yaml` + `.meta/chunks-index-<v>.yaml` |
| Phase 2：Impl 规划中 | 上述 + impl chunk 三态分布 + PRD→impl 映射关系 + 未覆盖的 PRD chunk 清单 | 同上 + SpecGraph |
| Phase 3：Merge 后（最终） | 上述 + 版本变更摘要（from baseline → to merged）+ 需求映射表（PRD chunk ↔ 用户需求）+ 健康度评分 | 同上 + merge commit 记录 |

## state.md 格式规范

### 初始版本（Phase 1）

```markdown
# 版本状态：v1.3

> 最后更新：2026-05-26T07:53:00Z | 更新者：ait-state skill | 触发事件：version create

## 元信息

| 字段 | 值 |
|---|---|
| 版本号 | v1.3 |
| 基于版本 | v1.2 |
| 创建时间 | 2026-05-26T07:53:00Z |
| 状态 | planning-prd |
| PRD 完成度 | 0 / 8 chunk（0%） |
| Impl 完成度 | —（PRD 未完成） |

## PRD Chunk 三态分布

| 状态 | 数量 | 占比 |
|---|---|---|
| ✅ committed | 0 | 0% |
| 📝 staged | 0 | 0% |
| ✏️ working | 8 | 100% |
| **合计** | **8** | **100%** |

## 当前 working 中的 PRD Chunk

| Chunk ID | 标题 | 创建时间 | 状态 |
|---|---|---|---|
| `prd-release-v13-overview` | v1.3 版本概述 | 2026-05-26 | working |
| `prd-backlog-v12-legacy` | v1.2 遗留实现清单 | 2026-05-26 | working |
| ... | ... | ... | ... |

## 需求映射（v1.3 覆盖的需求）

| 需求来源 | 需求描述 | 覆盖的 PRD chunk |
|---|---|---|
| v1.2 遗留 | `prd-skills-layout` 未实现 impl | `prd-backlog-v12-legacy` |
| `todo.md#1` | 参考项目 skill 功能迁移 | `prd-skill-migration` |
| `todo.md#2` | init 流程智能识别旧项目 | `prd-init-upgrade` |
| `todo.md#3` | links-index.yaml 重构为 SpecGraph | `prd-specgraph-index` |
| `todo.md#4` | 检索/聚焦读取命令行迁移 | `prd-search-cli` |
| 目标3 | state.md 版本进度面板 | `prd-skill-state` |
| v1.2 遗留 | `prd-skills-router` 等 5 个 chunk 的 impl | `prd-backlog-v12-legacy` |

## 健康度

- 🟡 PRD 规划进行中（0% 完成）
- 无阻塞项
```

### 中期版本（Phase 2，impl 规划中）

在 Phase 1 基础上增加：

```markdown
## Impl Chunk 三态分布

| 状态 | 数量 | 占比 |
|---|---|---|
| ✅ committed | 2 | 20% |
| 📝 staged | 1 | 10% |
| ✏️ working | 7 | 70% |
| **合计** | **10** | **100%** |

## PRD → Impl 覆盖情况

| PRD Chunk | 是否有 Impl | Impl Chunk | 覆盖状态 |
|---|---|---|---|
| `prd-release-v13-overview` | ✅ | `impl-v13-overview` | ✅ 已覆盖 |
| `prd-backlog-v12-legacy` | ✅ | `impl-v13-backlog` | ✅ 已覆盖 |
| ... | ... | ... | ... |
| `prd-skill-state` | ❌ | — | ⚠️ 未覆盖 |

## 未覆盖的 PRD Chunk（需要 impl 规划）

- `prd-skill-state`（ait-state skill 本身是否需要 impl？→ 需要，对应 `impl-v13-state-skill`）
```

### 最终版本（Phase 3，merge 后）

在 Phase 2 基础上增加：

```markdown
## 版本变更摘要

### 相较于 v1.2 baseline

**PRD 变更**：
- 新增 7 个 PRD chunk（`prd-v13-*`）
- 继承 v1.2 的 8 个 PRD chunk（通过 `based-on: v1.2`）

**Impl 变更**：
- 新增 10 个 impl chunk（`impl-v13-*`）
- v1.2 的 2 个 impl chunk 继续有效（已 committed）

### Merge 信息

| 字段 | 值 |
|---|---|
| Merge 时间 | 2026-06-01T10:00:00Z |
| Merge 触发者 | /ait version merge v1.3 |
| 冲突解决方式 | 无冲突（baseline 无后续提交） |

## 健康度评分

| 维度 | 评分 | 说明 |
|---|---|---|
| PRD 覆盖率 | 100% | 8 / 8 committed |
| Impl 覆盖率 | 100% | 10 / 10 committed |
| 需求覆盖率 | 100% | 6 / 6 需求有对应 PRD + impl |
| **综合评分** | **100%** | ✅ 版本健康 |

## 已知问题（Non-Goals 追踪）

- `ait-progress` / `ait-resume` 子 skill 本期仅占位，未完整实现（留 v1.4）
- `phases/` + `task/` 体系未引入（留 v1.4+）
- 语义搜索（embedding）未实现（留 v1.4+）
```

## ait-state Skill 设计

### 文件位置

`skill/ait/sub-skills/ait-state/SKILL.md`（新增子 skill）

### 触发语

```
INVOKE THIS SKILL when the user types `/ait state` or after any `version merge` operation to display the current version's progress panel (PRD distribution, impl coverage, health score).
```

### 行为流程

```
用户调用 /ait state
        │
        ▼
【Step 1】读取版本元信息
        └── cat .meta/versions/<current>.yaml
        │
        ▼
【Step 2】读取 chunks-index
        └── load .meta/chunks-index-<current>.yaml
        │
        ▼
【Step 3】读取 SpecGraph（如有）
        └── load .meta/specgraph.yaml
        │
        ▼
【Step 4】计算三态分布 + 覆盖率 + 健康度
        │
        ▼
【Step 5】渲染 state.md 内容（输出到终端 + 可选写入文件）
        │
        ▼
【Step 6】询问用户：是否写入 versions/<v>/state.md？
        └── y → bin/ait state save（写入文件）
        └── n → 仅终端显示
```

### CLI 接口

| 命令 | 用途 |
|---|---|
| `bin/ait state` | 显示当前版本状态（终端输出） |
| `bin/ait state --save` | 显示并写入 `versions/<v>/state.md` |
| `bin/ait state --version v1.2` | 查看指定版本状态 |
| `bin/ait state --format json` | JSON 格式输出（供 AI 解析） |

### 自动触发时机

| 触发事件 | 是否自动调用 ait-state |
|---|---|
| `bin/ait prd commit` | ✅ 自动调用（刷新 PRD 分布） |
| `bin/ait impl commit` | ✅ 自动调用（刷新 PRD + impl 分布） |
| `bin/ait version merge` | ✅ 自动调用（生成最终 state.md） |
| 用户手动 `/ait state` | ✅ 手动触发 |

## 与 v1.2 PRD 的关系

v1.2 `prd-skills-contract` 中定义了子 skill 的写入禁令：

> 子 skill 禁止直接写文件，必须通过 `bin/ait` CLI

**ait-state 遵守该契约**：
- `ait-state` 默认只**终端输出**，不写文件
- 写入 `state.md` 必须通过 `bin/ait state --save`（主 CLI 入口）
- 符合 v1.2 定义的子 skill 行为边界

## 验收标准

### state.md 内容验收

1. 版本创建后 `versions/v1.3/state.md` 存在（初始版本）
2. `state.md` 包含三态分布表（working/staged/committed）
3. `state.md` 包含需求映射表（PRD chunk ↔ 用户需求）
4. Impl commit 后，`state.md` 自动刷新，显示 impl 覆盖率
5. `version merge` 后，`state.md` 显示最终变更摘要 + 健康度评分

### ait-state skill 验收

1. `skill/ait/sub-skills/ait-state/SKILL.md` 存在
2. frontmatter description 以 `INVOKE THIS SKILL when` 起头
3. `bin/ait state --help` 显示 4 个子命令
4. `bin/ait state` 终端输出与 `state.md` 内容一致
5. `bin/ait state --save` 成功写入 `versions/<v>/state.md`
6. `bin/ait prd commit` 后自动刷新 `state.md`（验证自动触发）

## 非目标（本期不做）

| 非目标 | 留给后续 |
|---|---|
| state.md 的 Web UI 展示 | 不在 CLI 工具范围内 |
| 历史版本 state.md 的 diff 对比 | v1.4+ |
| state.md 的 AI 自然语言问答（"这个版本还差多少完成？"） | v1.4+（需要 AI 端支持） |

<!-- @id:prd-skill-migration -->

# 需求1：参考项目 skill 功能迁移

## 需求来源

`todo.md` 需求1：

> 把参考项目下：`/Users/jenningwang/PycharmProjects/version-design/tools/ait/templates/skills` 的 skill 功能放到当前项目中
> 约束要求：按照当前项目的规范来重新组织 skills；按照当前项目 init 的方式不改动；适配当前框架格式，增加新的流程

## 背景

参考项目 `version-design` 的 `tools/ait/templates/skills/` 目录下有一套 **micro-skill 模板**，包含：
- 子 skill 的 `SKILL.md` 模板
- 主 skill router 模板
- 各子 skill 的触发语模板

当前项目（`ait`）的 v1.2 PRD 已经规划了 micro-skill 拆分，但 **impl 未落地**。本 chunk 的职责是：**把参考项目的 skill 功能按当前项目规范重新组织，填入 v1.3 的 impl chunk 中**。

## 与 v1.2 PRD 的关系

本需求 **不是** 替代 v1.2 的 `prd-skills-*` 系列 chunk，而是 **为 v1.3 的 impl 提供"参考实现素材"**：

| v1.2 PRD chunk | 本需求提供的素材 |
|---|---|
| `prd-skills-layout` | 参考项目的 `sub-skills/` 目录结构模板 |
| `prd-skills-format-adapt` | 参考项目的 `SKILL.md` frontmatter + CLI Dependencies 模板 |
| `prd-skills-mapping` | 参考项目的 4 个子 skill 行为模板（ait-discuss / ait-impl-discuss / ait-progress / ait-resume） |
| `prd-skills-router` | 参考项目的主 SKILL.md router 模板 |

## 迁移原则

### 原则 1：术语对齐

| 参考项目术语 | 当前项目对齐 |
|---|---|
| `chunk-id` / `chunk` | 沿用（v1.2 已完成 block→chunk 重构） |
| `.planning/STATE.md` | 改为 `.meta/versions/<vX.Y>.yaml` + `.meta/chunks-index.yaml` |
| `.planning/ait/progress.json` | 改为 `.meta/chunks-index-<vX.Y>.yaml` |
| `.planning/ait/issues.md` | 本期不引入（留 v1.4+） |
| `ait list` / `ait draft new` | 改为 `bin/ait reindex` / `bin/ait prd create` / `bin/ait prd save-draft` |
| `ait progress show` | 本期用现有 CLI 组合实现（ait-progress 子 skill 内调用） |
| `ait resume` | 本期用现有 CLI 错误码字典实现（ait-resume 子 skill 内调用） |

### 原则 2：不改动 init

- 参考项目中可能有 `ait init` 的增强逻辑 → **不迁移到当前项目**
- 当前项目 `bin/ait` 的 init 流程保持不变
- 如需增强 init，走 `todo.md` 需求2 单独处理

### 原则 3：适配当前框架格式

参考项目的 `SKILL.md` 格式需要按当前项目规范调整：

| 维度 | 参考项目 | 当前项目规范 |
|---|---|---|
| frontmatter | `name` + `description` | 沿用，description 必须以 `INVOKE THIS SKILL when ...` 起头 |
| 触发语 | 可能不统一 | 每个子 skill 必须有明确 INVOKE 触发语，不重叠 |
| CLI 调用 | 直接调用 `ait <subcommand>` | 必须通过 `bin/ait <subcommand>`（相对路径或 PATH） |
| 写入路径 | 可能直接写文件 | 禁止直接写，必须通过 `bin/ait` CLI |
| 输出格式 | 可能 dump JSON | 必须复述关键字段，不原样 dump |

## 迁移内容清单

### 1. 主 skill router 模板

**来源**：参考项目主 `SKILL.md`

**迁移为**：当前项目 `skill/ait/SKILL.md` router 改造（对应 `impl-skills-router`）

**关键改动**：
- 删除 PRD 三阶段详细流程（下沉到 ait-discuss）
- 删除 impl 设计详细流程（下沉到 ait-impl-discuss）
- 保留：Project Layout、Commands 速查表、Common Pitfalls、MVP Scope Boundaries
- 新增：Sub-skills 索引段（列出 4 个子 skill 的 Trigger / Purpose）

### 2. ait-discuss 子 skill

**来源**：参考项目 PRD 讨论 skill

**迁移为**：`skill/ait/sub-skills/ait-discuss/SKILL.md`（对应 `impl-skills-mapping` + `impl-skills-format-adapt`）

**关键改动**：
- Clarify → Design → Generate 三阶段流程保留
- CLI 命令全部替换为当前项目 `bin/ait prd <subcommand>`
- 数据源从 `.planning/` 改为 `.meta/versions/` + `.meta/chunks-index.yaml`
- 输出契约：复述 `data` 关键字段，不 dump JSON

### 3. ait-impl-discuss 子 skill

**来源**：参考项目 impl 设计讨论 skill

**迁移为**：`skill/ait/sub-skills/ait-impl-discuss/SKILL.md`（对应 `impl-skills-mapping` + `impl-skills-format-adapt`）

**关键改动**：
- 为稳定 PRD chunk 驱动 impl 设计的流程保留
- CLI 命令全部替换为当前项目 `bin/ait impl <subcommand>`
- context 组装：调用 `bin/ait context <prd-chunk-id> --scenario prd-to-impl`
- 落盘：调用 `bin/ait impl create <prd-chunk-id> --content-file <tmp>`

### 4. ait-progress 子 skill（占位实现）

**来源**：参考项目 progress skill

**迁移为**：`skill/ait/sub-skills/ait-progress/SKILL.md`（对应 `impl-skills-mapping`，本期占位）

**关键改动**：
- 数据源从 `.planning/STATE.md` + `progress.json` 改为 `.meta/versions/<vX.Y>.yaml` + `.meta/chunks-index-<vX.Y>.yaml`
- 本期不引入新 CLI，子 skill 内调用 `bin/ait reindex` 后读 chunks-index 统计三态分布
- 渲染面板：Version / Requirements / Chunks{working,staged,committed} / Pending merges

### 5. ait-resume 子 skill（占位实现）

**来源**：参考项目 resume skill

**迁移为**：`skill/ait/sub-skills/ait-resume/SKILL.md`（对应 `impl-skills-mapping`，本期占位）

**关键改动**：
- 数据源从 `issues.md` 改为 CLI 错误码字典（PRD_NOT_COMMITTED / MERGE_CONFLICT / CHUNK_NOT_IN_VERSION / ID_FORMAT 等）
- 本期不引入新 CLI，子 skill 通过解析 `code` 字段给出恢复建议

## 不涉及迁移的内容（明确排除）

| 参考项目内容 | 排除原因 |
|---|---|
| `ait init` 增强逻辑 | todo.md 需求1 约束"按照当前项目 init 的方式不改动" |
| `.planning/phases/` 体系 | v1.2 non-goals，留 v1.4+ |
| `.planning/ait/issues.md` | 同上 |
| `ait next-up` CLI | 同上 |
| `ait build-tasks` / `ait execute` | 同上 |

## 验收标准

1. `skill/ait/sub-skills/` 下 4 个目录各含 `SKILL.md`
2. 每个 `SKILL.md` 的 frontmatter description 以 `INVOKE THIS SKILL when` 起头
3. 每个 `SKILL.md` 包含 CLI Dependencies 表（列出调用的 `bin/ait` 命令）
4. 每个 `SKILL.md` 包含 Artifacts 段（Reads / Writes / Side-effect）
5. 主 `SKILL.md` router 改造后 < 120 行，包含 Sub-skills 索引段
6. 全项目 `grep -r "直接写" skill/ait/sub-skills/` 命中数为 0（无直接文件写入）

<!-- @id:prd-init-upgrade -->

# 需求2：init 流程智能识别旧项目

## 需求来源

`todo.md` 需求2：

> 读取参考项目下的 ait init 实现方式，期望本项目中可以在 init 过程中，可以判断当前是新项目还是旧的项目，旧项目的话，判断是否有 project-docs 管理，如果有则跳过。如果没有，则引导客户把项目版本管理放到该
> 约束要求：按照当前项目的规范来重新组织 skills；按照当前项目 init 的方式不改动

## 背景

当前项目 `ait` 的 `bin/ait init` 功能（对应 `root.py` 中的 init 逻辑）是一个**固定流程**，不区分"新项目"和"已有 project-docs 的旧项目"。

参考项目 `version-design` 的 `ait init` 实现方式中，可能包含：
- 项目类型判断逻辑（新 / 旧）
- 已有 `project-docs/` 的检测
- 引导用户接入版本管理的交互流程

## 重要约束

> **按照当前项目 init 的方式不改动**

这意味着：**不修改 `bin/ait` 的 init 子命令入口，不修改 `root.py` 的 init 函数签名**。

本需求的实现方式是：**在现有 init 流程中调用一个新子 skill（`ait-init-check`），由子 skill 完成智能判断和引导，主流程不变**。

## 设计方案

### 架构：主流程 + 子 skill 增强

```
用户执行: bin/ait init
        │
        ▼
现有 init 流程（root.py）
        │
        ├── 原有逻辑：检查 project-docs/ 是否存在
        │
        └── 【新增】调用 ait-init-check 子 skill
                    │
                    ├── 判断项目类型（新 / 旧）
                    ├── 旧项目：检查是否有 project-docs 管理
                    │   └── 有 → 跳过，输出提示信息
                    └── 旧项目：无 project-docs
                        └── 引导用户：是否接入版本管理？→ 调用 bin/ait version create
```

### 子 Skill：`ait-init-check`

**文件位置**：`skill/ait/sub-skills/ait-init-check/SKILL.md`（新增，不在 v1.2 原规划中）

**触发语**：
```
INVOKE THIS SKILL when the user runs `bin/ait init` and the system needs to determine whether this is a new project or an existing project that already has project-docs management.
```

**职责**：
1. 判断项目类型：新项目（无 git 历史 / 空目录）/ 旧项目（有 git 历史 / 已有代码）
2. 旧项目：检查当前目录或父目录是否存在 `project-docs/`
3. 已有 `project-docs/` → 输出提示："项目已有版本管理，跳过 init"
4. 无 `project-docs/` → 引导用户选择：
   - 选项 A：接入版本管理（`bin/ait version create v0.1`）
   - 选项 B：跳过，保持当前状态

**CLI 依赖**（必须通过 `bin/ait` 调用，不直接写文件）：

| CLI 命令 | 用途 | 副作用 |
|---|---|---|
| `bin/ait version list` | 检查是否已有版本 | 无 |
| `bin/ait version create <vX.Y>` | 引导用户创建第一个版本 | 创建 `versions/<vX.Y>/` + `.meta/versions/<vX.Y>.yaml` |
| `ls project-docs/` | 检查 project-docs 是否存在 | 无 |

**Artifacts**：

| 操作 | 路径 | 方式 |
|---|---|---|
| 读 | `project-docs/`（存在性检查） | shell `ls` |
| 读 | `.meta/versions/*.yaml` | `bin/ait version list` |
| 写 | **无直接写入** | 所有写入通过 `bin/ait version create` |

### 对现有 init 流程的改动（最小侵入）

**改动范围**：仅 `root.py` 的 `init` 函数，**不改动 CLI 入口和参数解析**。

**改动内容**：

```python
# root.py - init() 函数内，在现有逻辑之后追加：

def init():
    """初始化项目版本管理（增强版：智能识别新/旧项目）"""
    # === 原有逻辑（不变）===
    if os.path.exists("project-docs/"):
        print("project-docs/ already exists. Use /ait to manage versions.")
        return

    # === 新增：调用 ait-init-check 子 skill（由 AI 驱动）===
    # AI 在读到这段逻辑时，会 INVOKE ait-init-check skill
    # 以下是给 AI 的提示（以注释形式存在于代码中，AI 可见）
    # AI_HINT: project is new or old? check git log / existing files.
    # AI_HINT: if old project without project-docs, guide user to `bin/ait version create`.
    #
    # 实际行为：AI 读到 init 被调用 → 触发 ait-init-check skill → skill 完成判断和引导

    # === 原有逻辑继续（不变）===
    os.makedirs("project-docs/versions/", exist_ok=True)
    # ...
```

**关键**：`root.py` 代码中的注释 `AI_HINT` 是给 AI 的触发信号，不是运行时逻辑。AI 在执行 `/ait init` 时读到这些注释，自动 INVOKE `ait-init-check` skill。

## 与 v1.2 PRD 的关系

v1.2 `prd-skills-non-goals` 明确写道：

> 不修改 init 流程（`skill/ait/bin/ait` 与 `root.py` 不动）

本需求 **不违反该 non-goal**，因为：
1. `bin/ait` CLI 入口和参数解析不动
2. `root.py` 的 `init()` 函数签名不动
3. 实际增强逻辑由子 skill（AI 驱动）完成，`root.py` 只是增加了 AI 可读的注释提示

## 验收标准

1. **新项目**（空目录 / 无 git）：`bin/ait init` → 正常创建 `project-docs/`（行为不变）
2. **旧项目 + 已有 `project-docs/`**：`bin/ait init` → 输出提示，跳过创建
3. **旧项目 + 无 `project-docs/`**：`bin/ait init` → AI INVOKE `ait-init-check` → 引导用户选择是否接入
4. `skill/ait/sub-skills/ait-init-check/SKILL.md` 存在，且 frontmatter description 以 `INVOKE THIS SKILL when` 起头
5. `grep -r "直接写\|echo >" skill/ait/sub-skills/ait-init-check/` 命中数为 0（无直接文件写入）
6. `bin/ait init --help` 输出不变（CLI 接口不变）

## 非目标（本期不做）

| 非目标 | 留给后续 |
|---|---|
| 自动检测参考项目 `version-design` 的 init 实现并迁移代码 | 本需求仅定义行为，不迁移参考项目代码 |
| 交互式 CLI 对话（如 `read -p "是否接入？[y/n]"`） | 由 AI 对话完成引导，不引入 CLI 交互 |
| 修改 `pyproject.toml` 或 `setup.py` | 无必要 |

<!-- @id:prd-specgraph-index -->

# 需求3：links-index.yaml 重构为 SpecGraph

## 需求来源

`todo.md` 需求3：

> prd 和 impl 之间的管理 links-index.yaml 格式修改为参考项目的方式，block 改为 chunk，使用参考项目中更加完善系统的 specgraph

## 背景

### 当前实现（v1.2）

当前项目使用 `.meta/links-index.yaml` 来管理 PRD chunk 与 impl chunk 之间的关联关系，格式简单：

```yaml
links:
  - prd_chunk: prd-xxx-overview
    impl_chunk: impl-xxx-overview
    relation: implements
```

**问题**：
1. 只有 `implements` 一种关系，无法表达 `depends_on` / `blocks` / `superseded_by` 等复杂关系
2. 没有 spec 来源的 URI 标准化（`spec:prd:<version>:<chunk-id>`）
3. 不支持跨版本 dependency graph 查询
4. 没有 weight / metadata 扩展能力

### 参考项目实现（version-design）

参考项目使用 **SpecGraph** 格式，核心概念：

| 概念 | 说明 |
|---|---|
| Spec URI | `spec:<type>:<version>:<chunk-id>`（标准化标识符） |
| Edge | `src` → `dst`，带 `rel` 类型 + `weight` + `metadata` |
| Graph | 有向图，支持拓扑排序、依赖分析、影响面分析 |
| Store | `.meta/specgraph.yaml`（替代 `links-index.yaml`） |

**参考项目 SpecGraph 格式示例**（预期格式，需从参考项目确认）：

```yaml
version: 1
specs:
  - uri: spec:prd:v1.2:prd-skills-overview
    title: 概述与目标
    type: prd
    version: v1.2
    chunk_id: prd-skills-overview
  - uri: spec:impl:v1.2:impl-skills-overview
    title: 概述与目标（实现）
    type: impl
    version: v1.2
    chunk_id: impl-skills-overview
edges:
  - src: spec:impl:v1.2:impl-skills-overview
    dst: spec:prd:v1.2:prd-skills-overview
    rel: implements
    weight: 1.0
    metadata:
      committed_at: '2026-05-25T05:45:35Z'
  - src: spec:prd:v1.3:prd-release-v13-overview
    dst: spec:prd:v1.2:prd-skills-overview
    rel: superseded_by
    weight: 1.0
    metadata: {}
```

## 设计方案

### Step 1：定义 SpecGraph 数据模型

**新增文件**：`ait/specgraph.py`

```python
# ait/specgraph.py

from dataclasses import dataclass, field
from typing import Optional, Dict, List
import yaml

@dataclass
class Spec:
    uri: str           # spec:<type>:<version>:<chunk-id>
    title: str
    type: str          # prd | impl
    version: str       # v1.2, v1.3, ...
    chunk_id: str
    metadata: Dict = field(default_factory=dict)

@dataclass
class Edge:
    src: str           # Spec.uri
    dst: str           # Spec.uri
    rel: str          # implements | depends_on | blocks | superseded_by | related
    weight: float = 1.0
    metadata: Dict = field(default_factory=dict)

@dataclass
class SpecGraph:
    version: int = 1
    specs: List[Spec] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)

    def add_spec(self, spec: Spec):
        if not any(s.uri == spec.uri for s in self.specs):
            self.specs.append(spec)

    def add_edge(self, edge: Edge):
        self.edges.append(edge)

    def get_impl_for_prd(self, prd_uri: str) -> Optional[Spec]:
        """查找实现指定 PRD spec 的 impl spec"""
        for e in self.edges:
            if e.dst == prd_uri and e.rel == "implements":
                return self.get_spec_by_uri(e.src)
        return None

    def get_prd_for_impl(self, impl_uri: str) -> Optional[Spec]:
        """查找 impl spec 实现的 PRD spec"""
        for e in self.edges:
            if e.src == impl_uri and e.rel == "implements":
                return self.get_spec_by_uri(e.dst)
        return None

    def get_dependencies(self, uri: str) -> List[Spec]:
        """获取指定 spec 的依赖（depends_on 关系）"""
        result = []
        for e in self.edges:
            if e.src == uri and e.rel == "depends_on":
                spec = self.get_spec_by_uri(e.dst)
                if spec:
                    result.append(spec)
        return result

    def topological_sort(self) -> List[Spec]:
        """拓扑排序（用于确定实现顺序）"""
        # Kahn's algorithm
        ...

    def to_dict(self) -> dict:
        ...

    @classmethod
    def from_dict(cls, d: dict) -> "SpecGraph":
        ...

    def save(self, path: str):
        with open(path, "w") as f:
            yaml.dump(self.to_dict(), f, allow_unicode=True)

    @classmethod
    def load(cls, path: str) -> "SpecGraph":
        with open(path) as f:
            d = yaml.safe_load(f)
        return cls.from_dict(d)

    # --- 辅助 ---
    def get_spec_by_uri(self, uri: str) -> Optional[Spec]:
        for s in self.specs:
            if s.uri == uri:
                return s
        return None
```

### Step 2：在 `bin/ait` 中新增 SpecGraph 子命令

**新增 CLI**：

| 命令 | 用途 |
|---|---|
| `bin/ait specgraph add-edge <src> <dst> --rel implements` | 手动添加 edge |
| `bin/ait specgraph query <uri> --deps` | 查询依赖 |
| `bin/ait specgraph query <uri> --implements` | 查询实现关系 |
| `bin/ait specgraph export --format dot` | 导出 Graphviz DOT（可视化） |
| `bin/ait specgraph sync` | 从现有 `links-index.yaml` 迁移数据 |

### Step 3：在 `bin/ait prd commit` 和 `bin/ait impl commit` 时自动维护 SpecGraph

**自动化规则**：

1. **PRD commit** 时：自动在 SpecGraph 中注册 `spec:prd:<version>:<chunk-id>`
2. **Impl create** 时：若 YAML frontmatter 含 `@ref ... rel:implements`，自动添加 `implements` edge
3. **Impl commit** 时：验证对应的 PRD chunk 已 committed（通过 SpecGraph 查询）

### Step 4：迁移现有 `links-index.yaml`

**迁移脚本**（由 `bin/ait specgraph sync` 执行）：

```python
def migrate_links_index():
    """从 .meta/links-index.yaml 迁移到 .meta/specgraph.yaml"""
    old = load_yaml(".meta/links-index.yaml")
    graph = SpecGraph()

    for link in old.get("links", []):
        prd_uri = f"spec:prd:v1.2:{link['prd_chunk']}"
        impl_uri = f"spec:impl:v1.2:{link['impl_chunk']}"

        # 注册 specs
        graph.add_spec(Spec(
            uri=prd_uri,
            title=link['prd_chunk'],
            type="prd",
            version="v1.2",
            chunk_id=link['prd_chunk']
        ))
        graph.add_spec(Spec(
            uri=impl_uri,
            title=link['impl_chunk'],
            type="impl",
            version="v1.2",
            chunk_id=link['impl_chunk']
        ))

        # 注册 edge
        graph.add_edge(Edge(
            src=impl_uri,
            dst=prd_uri,
            rel=link.get("relation", "implements")
        ))

    graph.save(".meta/specgraph.yaml")
```

## 与 v1.2 的关系

- v1.2 的 `links-index.yaml` **继续保留**（向后兼容），但新增操作同时写入 `specgraph.yaml`
- `bin/ait specgraph sync` 提供一次性迁移
- v1.4+ 可以考虑完全废弃 `links-index.yaml`

## 验收标准

1. `ait/specgraph.py` 存在，`SpecGraph` / `Spec` / `Edge` 可导入
2. `bin/ait specgraph --help` 显示 5 个子命令
3. `bin/ait specgraph sync` 能成功从 `.meta/links-index.yaml` 迁移数据到 `.meta/specgraph.yaml`
4. `bin/ait prd commit` 后，`.meta/specgraph.yaml` 中自动注册对应 `spec:prd:` 条目
5. `bin/ait impl create` 时，若内容含 `@ref ... rel:implements`，自动添加 edge
6. `bin/ait specgraph query spec:prd:v1.2:prd-skills-overview --implements` 返回正确的 impl spec URI
7. `bin/ait specgraph export --format dot` 输出合法的 Graphviz DOT 格式

## 非目标（本期不做）

| 非目标 | 留给后续 |
|---|---|
| 在 AI 对话中自动渲染依赖图（Mermaid） | v1.4+，需要 AI 端支持 |
| 跨版本 dependency conflict 检测 | v1.4+ |
| SpecGraph 的 Web UI 可视化 | 不在 CLI 工具范围内 |

<!-- @id:prd-search-cli -->

# 需求4：检索/聚焦读取命令行迁移

## 需求来源

`todo.md` 需求4：

> 参考项目中，检索/聚焦读取相关的命令行，挪到当前项目
> 结束要求：按照当前项目的实现规范

## 背景

参考项目 `version-design` 中有 **检索（search）** 和 **聚焦读取（focus）** 相关的命令行功能，当前项目（`ait`）尚未实现。

### 推测的功能范围（基于版本管理系统的常见需求）

| 功能 | 说明 | 参考项目可能的命令 |
|---|---|---|
| 检索 | 在全项目范围内搜索 chunk 内容（按关键词 / 语义） | `ait search <keyword>` / `ait search --semantic <query>` |
| 聚焦读取 | 只加载指定 chunk + 其关联 chunk（最小化上下文） | `ait focus <chunk-id>` / `ait context <chunk-id> --focus` |
| 依赖查询 | 查询 chunk 的依赖关系图谱 | `ait deps <chunk-id>` |
| 影响面分析 | 查询修改某个 chunk 会影响哪些其他 chunk | `ait impact <chunk-id>` |

## 与已有功能的关系

当前项目已有相关功能，需要**对齐而非重复**：

| 当前项目已有 | 参考项目可能有 | 处理方式 |
|---|---|---|
| `bin/ait context <chunk-id>`（L1+L2 上下文组装） | `ait focus` | 增强 `context` 命令，增加 `--focus` 模式（只返回 L1，不展开 L2） |
| `bin/ait reindex`（全量重新索引） | `ait scan` | 已对齐（v1.2 已完成） |
| 无 | `ait search` | **新增** |
| 无 | `ait deps` / `ait impact` | **新增**（基于 v1.3 的 SpecGraph） |

## 设计方案

### 新增命令 1：`bin/ait search <query>`

**功能**：在项目所有已 committed 的 PRD/impl chunk 中搜索关键词或语义匹配。

**实现**：

```python
# ait/search.py

import yaml
import os
import re
from typing import List, Dict, Tuple

def search_chunks(query: str, scope: str = "all", semantic: bool = False) -> List[Dict]:
    """
    Args:
        query: 搜索关键词
        scope: prd | impl | all
        semantic: 是否使用语义搜索（需要 embedding，v1.4+）
    """
    results = []
    index = load_chunks_index()

    for chunk in index["chunks"]:
        if scope == "prd" and not chunk["file"].startswith("prd/"):
            continue
        if scope == "impl" and not chunk["file"].startswith("impl/"):
            continue
        if chunk["state"] != "committed":
            continue  # 只搜索已 committed 的 chunk

        content = read_chunk_content(chunk)
        if match_chunk(content, query, semantic):
            results.append({
                "chunk_id": chunk["id"],
                "file": chunk["file"],
                "heading": chunk["heading"],
                "version": chunk["version"],
                "snippet": extract_snippet(content, query)
            })

    return results

def match_chunk(content: str, query: str, semantic: bool) -> bool:
    if semantic:
        # v1.4+：调用 embedding API
        return False
    else:
        # 关键词匹配（大小写不敏感）
        return query.lower() in content.lower()

def extract_snippet(content: str, query: str, context_lines: int = 2) -> str:
    """提取匹配行前后各 context_lines 行作为预览"""
    lines = content.split("\n")
    matches = []
    for i, line in enumerate(lines):
        if query.lower() in line.lower():
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            matches.append("\n".join(lines[start:end]))
    return "\n---\n".join(matches[:3])  # 最多 3 个匹配片段
```

**CLI 接口**：

```
bin/ait search "chunk 重命名" [--scope prd|impl|all] [--semantic]
```

**输出格式**：

```yaml
results:
  - chunk_id: prd-skills-rename-block-to-chunk
    file: versions/v1.2/prd/skills
    heading: Block 到 Chunk 的术语统一重构
    version: v1.2
    snippet: "当前项目的 block 在全项目重命名为 chunk..."
```

---

### 新增命令 2：`bin/ait focus <chunk-id>`（增强已有的 `context` 命令）

**功能**：只加载指定 chunk 本身（L1），不展开关联的 L2 chunk，用于"聚焦阅读"场景。

**与现有 `context` 的关系**：

| 命令 | 行为 |
|---|---|
| `bin/ait context <chunk-id>` | L1（目标 chunk）+ L2（@ref 关联 chunk）|
| `bin/ait context <chunk-id> --focus` | 仅 L1（目标 chunk 本身）|
| `bin/ait context <chunk-id> --deps` | L1 + 依赖图谱（基于 SpecGraph）|

**实现**（增强 `context.py`）：

```python
# ait/context.py - get_context() 函数新增 --focus 和 --deps 模式

def get_context(chunk_id: str, scenario: str = "default", focus: bool = False, deps: bool = False):
    # 读取目标 chunk（L1）
    target = read_chunk_file(chunk_id)

    if focus:
        # 仅返回 L1
        return {"L1": target, "L2": []}

    # 原有逻辑：读取 @ref 关联 chunk（L2）
    l2_chunks = extract_refs(target)

    if deps:
        # 基于 SpecGraph 读取依赖
        graph = SpecGraph.load(".meta/specgraph.yaml")
        uri = f"spec:{chunk_id.split('-')[0]}:{get_version(chunk_id)}:{chunk_id}"
        deps_specs = graph.get_dependencies(uri)
        l2_chunks += [spec.chunk_id for spec in deps_specs]

    return {"L1": target, "L2": l2_chunks}
```

---

### 新增命令 3：`bin/ait deps <chunk-id>`（基于 SpecGraph）

**功能**：查询指定 chunk 的依赖关系（depends_on）和被依赖关系。

**实现**：

```python
# ait/deps.py

def show_deps(chunk_id: str, direction: str = "both"):
    """
    Args:
        chunk_id: 目标 chunk
        direction: "in" (被依赖) / "out" (依赖别人) / "both"
    """
    graph = SpecGraph.load(".meta/specgraph.yaml")
    uri = spec_uri_for_chunk(chunk_id)

    result = {"chunk_id": chunk_id, "in": [], "out": []}

    for edge in graph.edges:
        if direction in ("both", "out") and edge.src == uri and edge.rel == "depends_on":
            dst_spec = graph.get_spec_by_uri(edge.dst)
            result["out"].append({"chunk_id": dst_spec.chunk_id, "title": dst_spec.title})
        if direction in ("both", "in") and edge.dst == uri and edge.rel == "depends_on":
            src_spec = graph.get_spec_by_uri(edge.src)
            result["in"].append({"chunk_id": src_spec.chunk_id, "title": src_spec.title})

    return result
```

**CLI 接口**：

```
bin/ait deps <chunk-id> [--direction in|out|both]
```

---

### 新增命令 4：`bin/ait impact <chunk-id>`

**功能**：修改某个 chunk 会影响哪些其他 chunk（反向依赖分析）。

**实现**：基于 SpecGraph 的**传递闭包**计算。

```python
# ait/impact.py

def compute_impact(chunk_id: str) -> List[Dict]:
    """计算修改 chunk_id 的影响面（所有反向依赖，传递）"""
    graph = SpecGraph.load(".meta/specgraph.yaml")
    uri = spec_uri_for_chunk(chunk_id)

    # BFS 反向遍历
    visited = set()
    queue = [uri]
    impact = []

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        for edge in graph.edges:
            if edge.dst == current and edge.rel in ("depends_on", "implements"):
                spec = graph.get_spec_by_uri(edge.src)
                impact.append({
                    "chunk_id": spec.chunk_id,
                    "title": spec.title,
                    "rel": edge.rel
                })
                queue.append(edge.src)

    return impact
```

**CLI 接口**：

```
bin/ait impact <chunk-id>
```

**输出示例**：

```yaml
impact_analysis:
  target: prd-skills-router
  affected_chunks:
    - chunk_id: impl-skills-router
      title: 主 SKILL.md Router 改造（实现）
      rel: implements
    - chunk_id: prd-skills-mapping
      title: 4 个 Skill 的迁移映射表
      rel: depends_on
```

## 验收标准

1. `bin/ait search "关键词"` 能返回匹配的 chunk 列表（含 snippet）
2. `bin/ait search "关键词" --scope prd` 只返回 PRD chunk
3. `bin/ait context <chunk-id> --focus` 只返回 L1（目标 chunk 本身）
4. `bin/ait context <chunk-id> --deps` 返回 L1 + SpecGraph 依赖
5. `bin/ait deps <chunk-id>` 返回依赖关系（in/out/both）
6. `bin/ait impact <chunk-id>` 返回影响面分析
7. 以上所有命令只读取 `state: committed` 的 chunk（不搜索 working/staged）
8. `ait/search.py`、`ait/deps.py`、`ait/impact.py` 文件存在，有对应的 CLI 注册

## 非目标（本期不做）

| 非目标 | 留给后续 |
|---|---|
| 语义搜索（embedding + vector store） | v1.4+，需要引入向量数据库 |
| 全文索引持久化（如 whoosh / elasticsearch） | v1.4+ |
| `ait search` 的 Web UI | 不在 CLI 工具范围内 |

<!-- @id:prd-task-relocation -->
## task YAML 目录从 .meta 迁到版本工作区

### 概述
当前 task YAML 落在 `.meta/tasks/{vX.Y}/T-*.yaml`，把"用户/AI 编辑读取的资产"放进了"系统索引账本"目录，与 `versions/{vX.Y}/` 已承载 `prd/`、`impl/`、`state.md` 的版本工作区心智不一致。本期把 task YAML 物理位置迁到 `versions/{vX.Y}/tasks/`，让一个版本的所有用户态资产同处一个目录。

### 业务规则
- task YAML 物理路径变更：`project-docs/versions/{vX.Y}/tasks/T-{源chunk}-NN.yaml`
- 所有 task 子命令读写新路径：`task create` / `task execute` / `task complete` / `task fail` / `task list` / `task show`
- `version reset <vX.Y> --confirm` 在物理删除版本时一并清除 `versions/{vX.Y}/tasks/`
- `version confirm <vX.Y>` 的前置守卫"task 必须全 done"按新路径扫描
- `.meta/` 不再保留 task YAML 单文件；如需要状态快照，由 `chunks-index-{vX.Y}.yaml` 增加 `tasks_summary` 字段在 reindex 时同步生成（counts: created/executing/done/failed）
- task-yaml schema chunk（`global/schema.md`）的路径示例同步更新
- 历史 `.meta/tasks/` 不做迁移：项目本身未真实使用过该路径，零数据；CLI 在启动时若发现旧路径存在，输出一次性告警并建议手动删除

### 验收标准
- [ ] `task create` 后，新文件出现在 `versions/{vX.Y}/tasks/T-*.yaml`，旧路径无新增
- [ ] `task list <vX.Y>` 能枚举新路径下所有 task 且数量正确
- [ ] `task execute` / `complete` / `fail` 全链路读写新路径，状态机闭环
- [ ] `version reset` 后 `versions/{vX.Y}/tasks/` 整目录被删除
- [ ] `version confirm` 在 task 未 done 时仍能正确拦截（错误码 `TASK_NOT_DONE` 不变）
- [ ] `chunks-index-{vX.Y}.yaml` 在 reindex 后含 `tasks_summary` 字段，计数与磁盘文件一致
- [ ] 主 SKILL.md 与 `global/schema.md` 中所有 task 路径引用同步更新

### 边界与非目标
- 不提供 `.meta/tasks/` → `versions/<v>/tasks/` 的自动迁移脚本（零数据）
- 不改 task YAML 的字段结构，仅改物理位置
- 不改 task 命名规则 `T-{源chunk}-NN.yaml`

<!-- @id:prd-init-incremental -->
## init 改为幂等的基线补全器

### 概述
当前 `bin/ait init` 在已有版本的项目上会以 `ALREADY_MANAGED` 错误码硬性拒绝，不区分"完整初始化"和"global 信息缺项"两种场景，导致用户在 global 不全时无法用 init 补齐，只能手工编辑文件。本期把 init 重定位为"幂等的差异补全器"：新项目走全量讨论，已纳管项目按缺项补全，已就绪项目报告状态退出。

### 业务规则
- 删除 `ALREADY_MANAGED` 这条 fail 出口；改为分支判别后走对应路径
- 三种场景：
  - **全新项目**：`project-docs/` 不存在或为空 → 走原全量讨论流程，生成 docs/global/ 全部骨架
  - **已纳管但 global 不全**：存在 `project-docs/` 但 `docs/global/` 下 `overview.md` / `tech-stack.md` / `ddl.md` / `schema.md` / `api.md` 任一缺失或仅含空骨架（无 `<!-- @id -->` 标记）→ 进入差异补全模式
  - **已就绪**：上述全部齐全 → 输出 `{"ok": true, "data": {"status": "ready", ...}}` 并退出
- 差异补全模式：
  - 由 `ait-init-guide` 子 skill（重定位自 `ait-init-check`）逐项讨论缺失文件
  - 每项补全前显式询问用户确认，拒绝则跳过该项
  - 仅写 `docs/global/`，不动 `versions/`、`docs/prd/`、`docs/impl/`、`.meta/specgraph.yaml` 中已有 chunk
  - 补全完成后调用 `reindex` 把新 chunk 注入 baseline `chunks-index.yaml` + `specgraph.yaml`
- 新增 `bin/ait init --check` 仅诊断不写入：返回 global 各项 present/missing 状态，方便 sub-skill 与用户预览
- "缺失"判定标准：文件不存在、文件大小为 0、或文件内容不含任何 `<!-- @id:global-* -->` 标记（仅占位骨架视为缺失）

### 验收标准
- [ ] 全新空目录 `bin/ait init` 行为不变（向后兼容）
- [ ] 已纳管但 `docs/global/tech-stack.md` 缺失时，`bin/ait init` 不再返回 `ALREADY_MANAGED`，进入补全流程
- [ ] 已就绪项目 `bin/ait init` 返回 `ok: true` + `status: ready`，不修改任何文件
- [ ] `bin/ait init --check` 输出 5 项 global 文件的 present/missing 字典
- [ ] 补全过程中用户拒绝某项，该项跳过且其他项继续
- [ ] 补全完成后 baseline `chunks-index.yaml` 与 `specgraph.yaml` 含新增 global chunk
- [ ] 不修改 `versions/`、`docs/prd/`、`docs/impl/` 任何已有内容
- [ ] 主 SKILL.md 的 Common Pitfalls 表移除 `ALREADY_MANAGED` 行

### 边界与非目标
- init 仍不创建版本号、不创建 `versions/{vX.Y}/` 目录
- 动态 global（ddl/schema/api）补全只生成空骨架（带 `<!-- @id -->`），真实内容仍由后续 version confirm 从 impl @extract 提取
- 不引入交互式 shell 输入（read -p）；逐项确认由 AI 对话完成
- 不支持选择性"重置某项 global 文件"（要重置仍需手动删文件后重跑 init）

<!-- @id:prd-skill-cli-resolution -->
## bin/ait 路径解析与 SKILL 文档约定修订

### 概述

SKILL.md 与 sub-skills 中所有 CLI 调用使用相对路径 `bin/ait ...`，AI 在用户项目根执行时可能因 cwd 不在 skill 安装目录而无法找到入口。本能力通过“文档约定 + 入口脚本自定位 + 项目本地 wrapper + 错误码兜底”保证 AI 从用户项目根也能正确调用 AIT。

v1.9 进一步修订安装更新行为：`install.py update` 应在更新 skill 文件后默认刷新安装目录内的 venv，使用户更新工具代码后无需额外手动重装；当用户明确传入 `--skip-venv` 时，才保留旧的“只更新文件、不刷新 venv”快速路径。

### 业务规则

- **文档层约定**：SKILL.md / 所有 sub-skill SKILL.md / references/* 中的业务 CLI 调用统一使用项目本地 wrapper `project-docs/.ait/ait-cli <subcmd>`；首次 init 引导命令仍使用 skill 安装目录下的绝对路径。
- **入口脚本自定位**：`bin/ait` shell wrapper 与 `bin/ait.cmd` 在执行前用脚本自身路径解析 venv 位置，不依赖 cwd；保证用户即便手动从绝对路径调用也能找到 venv 与 ait 包。
- **项目本地 wrapper**：`ait init` 负责生成 `project-docs/.ait/ait-cli` 或 `project-docs/.ait/ait-cli.cmd`，后续 PRD / impl / task / version 命令都从用户项目根通过该 wrapper 调用。
- **CLI cwd 校验**：AIT 子命令保持原有“必须从含 `project-docs/` 的用户项目目录运行”约束；该约束只校验用户业务 cwd，与 wrapper 自定位无关。
- **错误码兜底**：当 shell 抛出 `command not found` 或 `no such file or directory: bin/ait` 类错误时，sub-skill 必须能识别症状并提示用户改用 `project-docs/.ait/ait-cli` 或重新执行 `init --refresh-wrapper`。
- **install.py 更新默认刷新 venv**：`python install.py update` 在把仓库内 `skill/ait/` 文件同步到用户 skill 安装目录后，默认刷新该安装目录内 `.venv` 里的 AIT 包，使新代码在下一次 wrapper 调用时生效。
- **install.py 更新可跳过 venv**：`python install.py update --skip-venv` 只同步 skill 文件与文档，不刷新、不重建、不重新安装 `.venv` 内的 AIT 包；该选项用于用户明确需要快速文件更新或保留当前 venv 状态的场景。
- **命名约束**：跳过选项命名固定为 `--skip-venv`；不得改成 `--no-venv-warmup`、`--no-install` 或其他同义参数。
- **文档同步**：项目根 README 与 `skill/ait/README.md` 必须说明 `install.py update` 默认刷新 venv，以及 `--skip-venv` 的适用场景。

### 验收标准

- [ ] `grep -rn "bin/ait" skill/ait/SKILL.md skill/ait/sub-skills/` 命中数为 0（除非紧跟在 `${SKILL_DIR}/`、`~/.claude/skills/ait/` 或 wrapper 实现说明之后）。
- [ ] 主 SKILL.md 的 Global Contract 含项目本地 wrapper 入口约定。
- [ ] 用户在任意 cwd 执行 skill 安装目录下的 `bin/ait --version` 都能正常输出版本号。
- [ ] `bin/ait` wrapper 不依赖 `cd` 到特定目录才能找到 venv。
- [ ] Common Pitfalls 表包含 `ENOENT_BIN_AIT` 行：症状为 `no such file or directory: bin/ait`，恢复方式为改用项目本地 wrapper。
- [ ] 现有 sub-skill 的 CLI Dependencies 段全部使用项目本地 wrapper。
- [ ] `python install.py update` 默认会刷新安装目录 `.venv` 中的 AIT 包，更新后 wrapper 使用的是最新代码。
- [ ] `python install.py update --skip-venv` 不刷新 `.venv`，但仍同步 skill 文件与文档。
- [ ] 安装更新相关测试覆盖默认刷新 venv 与 `--skip-venv` 跳过路径。
- [ ] README 与 `skill/ait/README.md` 均记录新的 update 行为与参数。

### 边界与非目标

- 不引入系统级全局 `ait` 命令或 PATH 注入，保持显式路径调用哲学。
- 不改变 skill 默认安装目标，仍使用 `~/.claude/skills/ait/`。
- 不改变 CLI 子命令名与既有业务参数。
- 不引入环境变量 `AIT_HOME` 等可配置 skill 路径。
- 不要求 `install.py update --skip-venv` 修复已损坏的 venv；需要修复时用户应使用默认 update 或重新 install。

<!-- @id:prd-subskills-coverage -->
## sub-skills 治理：补齐 task 阶段、合并 progress/state、init-check 重定位

### 概述
当前 6 个 sub-skill 覆盖了 PRD/impl/接入诊断/进度/state/恢复 6 个场景，但 **task 阶段裸奔**（拆 task → AI 编码 → 收口由 main 直接处理，缺契约约束）；同时 `ait-progress` 与 `ait-state` 触发条件高度重叠（都读同一份状态数据），存在 AI 同时加载两个 skill 稀释 prompt 的风险。本期治理范围限定 3 件事：新增 task 执行 skill、合并 progress 入 state、重定位 init-check 为 init-guide。

### 业务规则

#### 规则 1：新增 ait-task-execute 子 skill
- 文件位置：`skill/ait/sub-skills/ait-task-execute/SKILL.md`
- 触发语：`INVOKE THIS SKILL when the user runs /ait task execute or asks to start coding a specific task`
- 职责：
  1. 调 `bin/ait task execute <id>` 拿到 token 聚焦的 context bundle（含 `impl_refs ∪ global_refs`）
  2. 驱动 AI 按 task YAML 的 `steps` 字段编码
  3. 编码完成后让用户/AI 执行 git commit 拿到 commit hash
  4. 调 `bin/ait task complete <id> --commit <hash> --path <files>` 收口
  5. 失败路径：调 `bin/ait task fail <id>` 后转交 `ait-resume`
- CLI Dependencies：`task execute` / `task complete` / `task fail` / `task show`
- Artifacts：Reads = task YAML + context bundle；Writes = 业务代码（由 AI 编辑工具落盘） + `task complete` 触发的 code_refs 回写；不直接写 `.meta/` 或 `versions/`
- 输出契约：每步必须复述 task id、commit hash、code_refs 路径

#### 规则 2：合并 ait-progress 进 ait-state
- 删除 `skill/ait/sub-skills/ait-progress/` 整个目录
- `ait-state` 扩展职责：兼任进度看板（原 progress 职责），既能渲染面板（`bin/ait state --version <v>`）又能落盘（`--save`），还能输出"未完成 chunk 列表"和"下一步建议"等进度叙述
- 触发语扩展为：`INVOKE THIS SKILL when the user asks to view AIT version state, refresh state.md, or check version progress / chunk three-state distribution / impl coverage`
- 主 SKILL.md 的速查表把 `/ait task list|show`、`/ait version status` 的 Routed skill 列从 `ait-progress` 改为 `ait-state`
- 主 SKILL.md 的 Sub-skills 索引表移除 `ait-progress` 行

#### 规则 3：ait-init-check 重定位并更名为 ait-init-guide
- 目录改名：`skill/ait/sub-skills/ait-init-check/` → `ait-init-guide/`
- 新职责：当 `bin/ait init` 进入"差异补全模式"（见 `prd-init-incremental`）时，逐项讨论用户要补哪些 global 文件，**不再做"新项目/旧项目"判别**（CLI 自己已能识别三种场景）
- 触发语改为：`INVOKE THIS SKILL when bin/ait init returns status=incomplete and the user needs to fill missing docs/global/* files interactively`
- CLI Dependencies：`bin/ait init --check`（诊断） / `bin/ait init`（执行补全） / `bin/ait reindex`
- 主 SKILL.md 的速查表把 `/ait init` 的 Routed skill 从 `ait-init-check` 改为 `ait-init-guide`

#### 规则 4：触发关键词去重与契约一致性
- 所有保留的 sub-skill（ait-discuss / ait-impl-discuss / ait-init-guide / ait-state / ait-resume / ait-task-execute）的 `description` 触发语两两不重叠
- 每个 sub-skill 的 CLI Dependencies / Artifacts / Output Contract / Common Pitfalls 四段必须完整
- 写入路径仍受主 SKILL.md Global Contract 限制（不直接写 `docs/` / `.meta/` / `versions/`）

### 验收标准
- [ ] `skill/ait/sub-skills/ait-task-execute/SKILL.md` 存在且四段完整（CLI Dependencies / Artifacts / Workflow / Common Pitfalls）
- [ ] `skill/ait/sub-skills/ait-progress/` 目录被删除
- [ ] `skill/ait/sub-skills/ait-init-guide/SKILL.md` 存在；旧 `ait-init-check/` 目录被删除
- [ ] `ait-state/SKILL.md` 的 description 触发语包含 progress / 进度 / 完成度 等关键词
- [ ] 主 SKILL.md 速查表的 Routed skill 列与 Sub-skills 索引表均同步更新（progress 全部替换为 state；init-check 替换为 init-guide）
- [ ] `grep -r "ait-progress\|ait-init-check" skill/ait/` 命中数为 0
- [ ] 6 个 sub-skill 的触发语两两不重叠（人工 review 通过）
- [ ] `/ait task execute` 端到端走通：CLI → ait-task-execute skill → AI 编码 → task complete

### 边界与非目标
- 不为 `prd commit` / `impl commit` / `version confirm` / `version reset` 单独建 sub-skill（单步 CLI 调用，main 路由足够）
- 不引入 `ait-task-create` 子 skill（拆 task 当前由 main 处理，复杂度未到需要独立 skill 的程度）
- 不重写所有现有 sub-skill 的 description（仅 ait-state 与 ait-init-guide 必需修改）
- 不引入 sub-skill 之间的显式调用链（仍由 AI 根据触发条件自主切换）

<!-- @ref:prd/ait-redesign#prd-task-stage rel:supersedes-path -->
<!-- @ref:prd/ait-redesign#prd-init rel:refines -->
<!-- @ref:prd/skills#prd-skills-overview rel:refines -->

<!-- @id:prd-prd-global-single-file -->
## prd-global-single-file: Baseline PRD 单文件化

### 概述

把 baseline 的 PRD 物理布局从"`docs/prd/*.md` 多文件散落"统一为"`docs/prd/global.md` 单文件"，让 global PRD 在文件系统层就是一个清晰的实体；同时保留 chunk 作为唯一规划/合并单位的语义。impl 文件布局保持多文件不变，由 PRD chunk 通过 `@ref` 锚定关联。

### 业务规则

- 新基线契约：v1.6 起 baseline PRD 唯一文件为 `docs/prd/global.md`
- 一次性迁移（v1.6 内执行一次，作为本版本第一组 task 落地）：
  - 把现有 `docs/prd/` 下 14 个 PRD 文件的全部 chunk 按当前 chunks-index 顺序拼接到 `docs/prd/global.md`
  - 每个 chunk 内容、`@id`、`@ref`、`@extract` 全部保留不变（chunk_parser 自反性自检）
  - 物理删除迁移源文件
  - 调用 `ait reindex` 重建 baseline `chunks-index.yaml` + `specgraph.yaml`
  - 校验：迁移前后 chunk 数量、id 集合、`@ref` 关系全等
- CLI 路径写入策略调整：
  - `prd commit` 时对 `versions/{vX.Y}/prd/` 下任意 `*.md` 解析出的 chunk，merge 时全部合入 `docs/prd/global.md`，不再保留版本里的多文件物理结构到 baseline
  - 版本工作区仍可多文件（人写起来更舒服），但 baseline 永远单文件
- 历史版本兼容：
  - 已 merged 的 v1.1~v1.5 不动其 `versions/{vX.Y}/prd/` 历史快照
  - `chunks-index-{vX.Y}.yaml` 历史也不动
  - 仅 baseline `chunks-index.yaml` 在迁移后所有 chunk 的 `file` 字段统一为 `prd/global`

### 验收标准

- [ ] `docs/prd/global.md` 存在，包含原 14 个 PRD 文件的所有 chunk
- [ ] `docs/prd/` 下不再有其他 `.md` 文件（仅 `global.md`）
- [ ] `ait reindex` 后 `chunks-index.yaml` 中所有 PRD chunk 的 `file` 字段均为 `prd/global`
- [ ] 迁移前后 chunk id 集合相等、`@ref` 关系图同构（specgraph diff = 0）
- [ ] `chunk_parser.parse_file(global.md)` 解析出的 chunk 数 = 迁移前所有 PRD 文件 chunk 数之和
- [ ] 现有所有 `ait state` / `ait specgraph` / `ait deps` / `ait impact` 命令仍正常工作

### 边界与非目标

- 不改 impl 文件布局：`docs/impl/*.md` 仍可多文件
- 不改 chunk 的 `@id` / `@ref` / `@extract` 语法
- 不改版本工作区的写入路径：版本仍可在 `versions/{vX.Y}/prd/<file>.md` 下任意命名（CLI 在 confirm/merge 时把 chunk 缝合进 `global.md`）

<!-- @id:prd-prd-chunk-summary-index -->
## prd-chunk-summary-index: chunks-index 增加 summary 字段

### 概述

为每个 chunk 在 `chunks-index.yaml` 中增加一个短摘要字段，让 `/ait prd create` 在递归读 baseline 时只读 index 不读全文，把基线扫描的 token 消耗压到原来的 1/20 量级。summary 仅在 index 里维护，不写进 markdown 正文，纯辅助元数据。

### 业务规则

- schema 扩展（向后兼容），index 中每个 chunk 增加可选字段：
  ```yaml
  chunks:
    - id: prd-task-relocation
      file: prd/global
      heading: task relocation
      level: 2
      summary: "Move task YAML from .meta/tasks to versions/{vX}/tasks; add legacy warn"
  ```
- summary 约束：≤ 120 字符的中文/英文一句话摘要；字段可缺省；旧数据 reindex 时 summary 为 `null`，由后续 commit/手动补齐
- 生成时机：
  - `prd commit` / `impl commit` 锁定时，CLI 调用 ait-discuss skill 钩子让 LLM 生成 summary，写入 chunks-index
  - 也允许在 markdown 里用 `<!-- @summary: ... -->` 元注释直接声明（优先级高于 LLM 生成）
- 新命令 `ait baseline-summary [--scope prd|impl|all] [--format yaml|json]`：输出 baseline 所有 chunk 的 `id + heading + summary` 列表，供 ait-discuss skill 在 `/ait prd create` 时一次性读入
- `ait reindex` 兼容性：保留已有 summary 字段，仅刷新 `id` / `file` / `heading` / `level`

### 验收标准

- [ ] `chunks-index.yaml` 新增的 `summary` 字段被现有解析代码忽略时不报错（向后兼容）
- [ ] `ait baseline-summary --scope prd` 输出当前 baseline 所有 PRD chunk 的 `id + summary`
- [ ] `prd commit` 后该 commit 涉及的所有 chunk 在 baseline `chunks-index.yaml` 中都有非空 summary（commit 时若 LLM 钩子失败必须报错而非静默写空）
- [ ] markdown 里 `<!-- @summary: xxx -->` 注释能正确被读取并写入 index（优先级覆盖 LLM 生成值）
- [ ] `ait reindex` 不丢失已存在的 summary 字段

### 边界与非目标

- 不用 embedding / 向量库（保留为 v1.7+ 可选增强）
- 不改 chunk 内文档语法（summary 只在 index 里，不写进 markdown 正文）
- summary 不参与合并冲突检测，不参与 `@id` / `@ref` 解析

<!-- @id:prd-prd-recursive-modify-discovery -->
## prd-recursive-modify-discovery: prd create 时基于 baseline 讨论并确认 modify

### 概述

`/ait prd create "<title>"` 必须把当前 baseline PRD chunk 摘要作为讨论输入交给 AI，用于辅助识别本次需求可能涉及的旧 PRD chunk。AI 只能提出 add/modify 建议，不能直接把 modify 决议写入版本工作区；任何修改旧 chunk 的决议都必须先展示给用户确认。

v1.10 明确 PRD modify 的内容契约：版本侧 modify chunk 是完整替换块，不是 patch。用户确认某个 baseline chunk 被 modify 后，写入 `versions/<v>/prd/*.md` 的新 chunk 必须包含该 chunk 合并后的完整内容，包括旧 chunk 中仍然有效的全部信息和本次新增/修改的信息。merge 时直接用该完整 chunk 替换 `overrides` 指向的 baseline chunk。

### 业务规则

- ait-discuss 在 PRD 讨论开始时调用 `project-docs/.ait/ait-cli baseline-summary --scope prd --format yaml`，把 baseline 的 `id + heading + summary` 作为讨论上下文。
- AI 与用户完成需求讨论后，再根据最终 PRD 拆分结果标出每个 PRD chunk 是新增还是修改旧 chunk。
- 所有 `modify` 候选必须展示给用户确认，展示字段至少包含 `new_id`、`action`、`overrides`、`confidence`、`reason`。
- 对每个被确认的 `modify` 候选，ait-discuss 必须读取 `overrides` 指向的旧 chunk 全文，并在生成新 PRD chunk 时保留旧 chunk 中仍然有效的信息。
- 用户确认后的版本侧 modify chunk 必须是完整替换块。它不能只写新增段落、差异片段、补丁说明或“沿用旧内容”的引用。
- merge 层不做旧内容补全；若版本侧 modify chunk 缺少应保留的信息，merge 后这些信息会丢失，责任在 PRD 讨论/确认阶段完成。
- 用户确认前，skill 不得调用 `prd resolve-candidates`，也不得把 AI 原始判断写入 `.candidates.yaml`。
- 用户可以拒绝某个 modify，将其改为 add；也可以手工调整 `overrides` 指向的 baseline chunk。
- 用户确认后，skill 沿用现有 `prd resolve-candidates --from-file <file>` 落盘确认后的 candidates，不新增 change plan 文件、schema 或命令。
- 如果最终 PRD chunk 使用 baseline 已有 id，CLI 可按现有规则将其登记为 `action: modify, overrides: <same-id>`；如果使用新 id 修改旧 chunk，则必须通过确认后的 candidates 提供 `overrides`。
- `delete_candidates` 默认为空；删除旧 PRD chunk 仍要求用户显式声明，不由 AI 自动提出。

### 验收标准

- [ ] ait-discuss 的工作流明确要求先读取 baseline summary 并用于 PRD 讨论。
- [ ] ait-discuss 明确区分 AI 建议与用户确认后的 candidates。
- [ ] skill 文档中写明：未获得用户确认前不得调用 `prd resolve-candidates`。
- [ ] skill 文档中写明：PRD modify chunk 必须包含旧 chunk 中仍然有效的全部信息，是完整替换块。
- [ ] 用户确认后的 PRD modify 仍使用现有 `.candidates.yaml` / `action` / `overrides` 机制。
- [ ] 未新增 change plan 概念、文件或 CLI 命令。
- [ ] 既有 `prd resolve-candidates`、`prd save-draft`、`prd commit` 的校验语义保持兼容。

### 边界与非目标

- 不让 CLI 自行做语义判断；语义识别仍由 skill 侧 AI 讨论完成。
- 不把 AI 原始候选视为用户确认结果。
- 不新增独立的 change plan 抽象。
- 不做语义 diff 或 patch；modify 仍是 chunk 级完整替换。
- 不要求 merge 层从旧 chunk 自动补全缺失内容。

<!-- @id:prd-prd-chunk-atomic-impl-merge -->
## prd-chunk-atomic-impl-merge: impl 侧基于 baseline 讨论并确认 modify/inherit

### 概述

impl 阶段必须遵循与 PRD 阶段一致的人机确认逻辑：`/ait impl create <prd-chunk-id>` 在生成实现设计前，应读取当前 PRD chunk、其覆盖的旧 PRD chunk（若存在）以及旧 PRD chunk 在 baseline 中对应的 impl chunks。AI 可以建议新增、修改或继承 impl，但任何修改旧 impl 或继承旧 impl 的动作都必须先由用户确认。

v1.10 修正 inherit 的 merge 语义：继承旧 impl 表示该 baseline impl 对当前版本仍然有效，它可以参与当前版本的上下文、覆盖判断和 task 拆分，但不得作为新增 chunk 再写入 baseline。baseline 中已经存在的 inherited impl 不应被追加第二份。

### 业务规则

- ait-impl-discuss 在 impl 讨论开始时调用 `context <prd-chunk-id> --scenario prd-to-impl` 获取当前 PRD 上下文。
- 如果当前 PRD chunk 是 `action: modify` 且有 `overrides`，skill 需要读取 `overrides` 指向的旧 PRD chunk，并通过 specgraph 找到 baseline 中实现该旧 PRD chunk 的 impl chunks。
- AI 与用户完成实现讨论后，再标出 impl chunk 的新增、修改或继承建议。
- 对 `modify` 旧 impl 的建议，skill 必须展示 `new_id`、`overrides`、`reason` 并获得用户确认后，才允许生成可落盘的 impl draft。
- 对 `inherit` 旧 impl 的建议，skill 必须展示将被继承的 baseline impl chunk 列表并获得用户确认后，才允许调用现有 `ait impl inherit <prd-chunk-id>`。
- `inherit` 是 skill/命令层的工效动作，用于把 baseline impl 带入当前版本上下文。它不得在 merge 阶段表现为 `action=add` 写入 baseline。
- 不新增 `action: inherit` 到 schema。实现可以用同 ID `action=modify, overrides=<impl-id>` 表示“保留该 baseline impl”，或在 merge 前过滤 inherited/no-op 记录；无论采用哪种内部表示，version confirm 后 baseline 不得出现重复 chunk。
- 为了让确认后的 impl modify 能确定性落盘，`ait impl create` 需要支持显式 `--action modify --overrides <baseline-impl-id>` 参数，并在 CLI 层校验 overrides 存在于 baseline。
- 未指定 `--action` 时，`impl create` 保持现有默认行为：创建新增 impl chunk，登记为 `action: add`。
- merge 前必须阻断任何 `action=add` 且 chunk id 已存在于 baseline 的 impl 记录，避免把继承或误分类的旧 impl 追加进 baseline。

### 验收标准

- [ ] ait-impl-discuss 的工作流明确读取当前 PRD、旧 PRD（若有）和旧 PRD 对应的 baseline impl chunks。
- [ ] 修改旧 impl 前，skill 必须向用户展示 `overrides` 候选并等待确认。
- [ ] 继承旧 impl 前，skill 必须向用户展示将继承的 impl 列表并等待确认。
- [ ] `ait impl create` 支持 `--action modify --overrides <impl-id>`，并把版本索引记录写为 `action: modify`、`overrides: <impl-id>`。
- [ ] `--action modify` 缺少 `--overrides` 时失败；`overrides` 不在 baseline 时失败。
- [ ] `ait impl inherit <prd-chunk-id>` 后执行 version confirm，不会向 baseline 追加重复 inherited impl chunk。
- [ ] merge 前发现 `action=add` 且 baseline 已有同 ID chunk 时会阻断。
- [ ] 未新增 change plan 概念、文件或 CLI 命令。

### 边界与非目标

- 不引入 `action: inherit` 到版本索引 schema。
- 不让 `impl create` 自动猜测要覆盖哪个 baseline impl；覆盖目标必须来自用户确认后的显式参数。
- 不做 impl 级语义 diff；modify 仍是完整 chunk 替换。
- 不改变 PRD chunk 原子替换 impl 集合的既有 merge 规则，只修正 inherited impl 的 baseline 写入语义。

<!-- @id:prd-prd-format-enforcement -->
## prd-format-enforcement: PRD/impl 格式规范强制化

### 概述

v1.5 已通过 `prd-formats` chunk 规范了 PRD 四段（`概述` / `业务规则` / `验收标准` / `边界与非目标`）、impl chunk `@extract` 标记、task YAML 字段、派生命名（`impl-{源chunk}-{名}` / `T-{源chunk}-NN`）、chunk id 命名（`{type}-{domain}-{name}` 小写短横线）。但当前 `impl-formats-parser` 仅给出告警、不阻断 commit，导致 v1.6 PRD 草稿曾用英文四段（Goal/Non-Goals/Approach/Acceptance）也通过了 `prd save-draft` / `prd confirm`。本期把规范从"软提示"升级为"硬约束"：在 commit 闸门强制阻断违规，并提供 `ait lint` 离线扫描+机械修复命令；同时 v1.6 的本期重写已自纠为合规（dogfood）。

### 业务规则

- **`prd commit` 闸门**：所有 PRD chunk 必须包含且仅包含中文四段三级标题：`### 概述` / `### 业务规则` / `### 验收标准` / `### 边界与非目标`；缺段、英文段名、段名顺序错乱 → 报错码 `PRD_FORMAT_VIOLATION`，错误体含违规 chunk id 与缺段/错段清单，阻断提交
- **`impl commit` 闸门**：impl chunk 含代码块（` ``` ` 围栏）时必须用 `<!-- @extract:dynamic/{type}#{chunk} -->` ... `<!-- @extract-end -->` 包裹该代码块；纯说明性 impl chunk（无代码块）不强制要求 @extract；违规 → `IMPL_FORMAT_VIOLATION`
- **chunk id 命名校验**：`{type}-{domain}-{name}`，`type ∈ {prd, impl, task, global}`，全小写短横线（仅允许 `[a-z0-9-]`）；违规 → `CHUNK_ID_FORMAT_VIOLATION`
- **派生命名校验**：
  - impl chunk id 必须形如 `impl-{源 PRD chunk 去掉 prd- 前缀}-{名}`，且其 `@ref ... rel:implements` 指向的 PRD chunk id 必须存在
  - task YAML id 必须形如 `T-{源 chunk}-NN`（NN 为 2 位数字）
  - 违规 → `DERIVED_NAME_VIOLATION`
- **新命令 `ait lint [--scope baseline|version|<vX.Y>] [--fix]`**：
  - 离线扫描指定 scope 内所有 chunk，输出违规清单（JSON 数组，含 `chunk_id` / `code` / `message` / `fixable`）
  - `--fix` 仅修可机械修复的项：四段标题英文 → 中文映射（Goal→概述、Non-Goals→边界与非目标、Approach→业务规则、Acceptance→验收标准）、缺段填空骨架（`### <段名>\n\n_TODO_\n`）；不可机械修复的违规仅报告不修改
  - 默认 scope 为 `baseline`；`--scope version` 等价于扫描所有未 merged 版本工作区
- **错误码退出策略**：违规时 CLI 退出码非零；stdout 仍输出 `{"ok": false, "error": {...}}` 契约 JSON；错误体包含违规清单数组，每项含 `chunk_id` / `file` / `line` / `code` / `message`
- **v1.6 自我修复（dogfood）**：本版本 PRD 重写时 4 个原 chunk 已手工改为中文四段并保持 chunk id 不变；不再依赖 `--fix`（避免鸡生蛋）；新增的 `prd-prd-format-enforcement` 也以中文四段交付
- **闸门生效时机**：`prd commit` / `impl commit` 闸门在本期 impl 落地后立即生效，对 v1.6 自身及后续所有版本均强制；baseline 的存量历史 chunk 不做回溯校验（仅在 `ait lint --scope baseline` 主动扫描时报告）

### 验收标准

- [ ] `ait prd commit` 在含英文四段（Goal/Non-Goals/Approach/Acceptance）的 PRD chunk 上报 `PRD_FORMAT_VIOLATION` 并阻断
- [ ] `ait prd commit` 在缺任一中文四段时报 `PRD_FORMAT_VIOLATION` 并列出缺段名
- [ ] `ait impl commit` 在 impl chunk 含裸代码块（无 `@extract` 包裹）时报 `IMPL_FORMAT_VIOLATION`
- [ ] `ait lint --scope v1.6` 列出 v1.6 所有 5 个 chunk 的格式违规（重写后应为 0 条违规）
- [ ] `ait lint --scope baseline --fix` 在 baseline 历史 chunk 上能机械修复英文四段（若存在），且修复后 `ait lint --scope baseline` 通过
- [ ] 派生命名违规（如出现 `impl-foo-bar` 但 baseline 与所有版本都不存在 `prd-foo`）报 `DERIVED_NAME_VIOLATION`
- [ ] chunk id 含大写、下划线、空格时报 `CHUNK_ID_FORMAT_VIOLATION`
- [ ] task YAML id 不符合 `T-{源 chunk}-NN` 格式时报 `DERIVED_NAME_VIOLATION`
- [ ] 所有违规错误码退出非零，stdout 输出合法 `{"ok": false, "error": {...}}` JSON
- [ ] v1.6 本身 5 个 chunk 在本版本 impl 落地后跑 `ait prd commit` 不触发任何格式违规（dogfood 自洽）

### 边界与非目标

- 不做语义级 lint（不判断"验收标准"是否覆盖"概述"目标、不查"边界与非目标"是否合理）
- 不自动改写 chunk 正文内容；`--fix` 仅做机械的标题映射 / 缺段空骨架填充
- 不改 chunk id 命名规则本身（沿用 v1.5 `prd-formats` 已定的派生式 + 三段式）
- 不强制 task YAML 字段级 lint（task 由 `task create/execute` 内置 schema 校验，已足够）
- 不对历史已 merged 版本（v1.1 ~ v1.5）做强制回溯阻断（仅 `ait lint --scope baseline` 主动扫描时报告，不阻断任何写操作）
- 不引入新的格式（如 YAML frontmatter、JSON Schema 文件），保持 HTML 注释元数据哲学

<!-- @ref:prd/ait-redesign#prd-formats rel:refines -->

<!-- @id:prd-test-spec-alignment -->
## Test and Spec Alignment

### 概述
v1.7 的首要目标是让当前测试套件重新回到全绿状态，并把测试、文档示例和代码中的关系索引预期统一到现行设计。

当前已知失败集中在两处：`docs/prd/global.md` 中的示例 `@ref:file#block-id` 被解析成真实引用并形成 dangling target；`test_index_manager.py` 仍断言已废弃的 `links-index` 包含 `implements` 关系。

### 业务规则
- AIT 的关系真相源是 `specgraph`，新测试和主路径文档不再把 `links-index.yaml` 作为主要关系索引。
- 文档中展示字面量 `@ref` 语法时，示例不得被真实解析器误识别为跨 chunk 引用，除非示例目标确实存在。
- `IndexManager.rebuild_baseline()` 的回归测试只校验 baseline chunk index 写入；关系断言应改为通过 `sync_specgraph()` 或 `SpecGraph` 查询完成。
- 真实 Markdown 中位于代码块外的有效 `@ref` 仍必须被解析并进入 specgraph。
- 本版本范围只覆盖当前失败测试和相关规范收口，不引入新的用户命令。

### 验收标准
- [ ] `python -m pytest -q` 全部通过。
- [ ] `test_chunk_parser_global.py::test_large_single_file_parses_full` 不再报告 dangling target `block-id`。
- [ ] `test_index_manager.py::test_rebuild_baseline_writes_files` 或其替代测试不再依赖 `links-index` 的 `implements` 返回值。
- [ ] 测试和主路径文档中的关系索引描述统一指向 `specgraph`。
- [ ] 如果修改解析行为，必须补充聚焦测试，证明真实 `@ref` 仍会被解析，示例片段不会误入关系图。

### 边界与非目标
- 不处理 baseline 历史文档的大规模 `lint --scope baseline` 格式债务。
- 不实现 `ait doctor`。
- 不调整 task、version confirm 或动态 global 的业务流程。
- 不做全局 Codex skill 安装策略变更。

<!-- @id:prd-cli-file-option-names -->
## CLI file options accept file names only

### 概述

AIT CLI file options for creating version-side PRD and Impl markdown must accept only a file name. The command layer owns the domain directory mapping so callers cannot accidentally write files at the version root or into arbitrary subpaths.

### 业务规则

- `ait prd confirm <req-id> --file <name>` writes `versions/<v>/prd/<name>.md` and reports the canonical file key `prd/<name>`.
- `ait impl create <prd-chunk-id> --impl-file <name>` writes `versions/<v>/impl/<name>.md` and reports the canonical file key `impl/<name>`.
- `ait impl create ... --prd-file <name>` resolves the explicit PRD file as `prd/<name>`.
- File option values must be rejected with `INVALID_FILE_NAME` when empty, equal to `.` or `..`, contain `/`, `\`, or `:`, or end with `.md`.
- Commands that read or commit already-materialized files continue to use canonical file keys such as `prd/<name>` and `impl/<name>`.
- AIT skill instructions and user-facing command examples must show bare file names for these create/confirm options.

### 验收标准

- A CLI regression proves `--file path-check` writes `versions/<v>/prd/path-check.md` and does not create `versions/<v>/path-check.md`.
- A CLI regression proves `--impl-file version` writes `versions/<v>/impl/version.md` and does not create `versions/<v>/version.md`.
- CLI regressions reject `--file prd/path-check`, `--impl-file impl/version`, and `--prd-file prd/path-check` with `INVALID_FILE_NAME`.
- Existing PRD show/commit and impl commit flows continue to operate on canonical file keys.
- The full test suite passes.

### 边界与非目标

- Do not migrate already-merged historical version workspaces in this change.
- Do not change the persisted index format; it continues to store canonical file keys with `prd/` and `impl/` prefixes.
- Do not change automatic impl file detection, except that explicit CLI file options are normalized before reaching the manager layer.

<!-- @id:prd-v2-prd-fsd-tdd-parallel-model -->
## v2.0 introduces parallel PRD/FSD/TDD model

### 概述

AIT currently uses a PRD/impl/task workflow. v2.0 must keep that workflow available so v2.0 itself can be developed through current AIT dogfood, while adding a new PRD/FSD/TDD model for later versions.

The target model separates intent, decomposition, and code generation instructions:

- PRD describes requirements: why and what.
- FSD describes functional decomposition and interaction contracts.
- TDD describes the concrete technical implementation of one target code file.

### 业务规则

- v2.0 development itself must use the current AIT PRD/impl/task flow.
- v2.0 must introduce PRD/FSD/TDD as parallel capability, not replace the old workflow immediately.
- Existing `ait prd`, `ait impl`, and `ait task` commands remain available.
- New capability is exposed through `ait fsd`, `ait tdd`, and `ait codegen`.
- v2.0 must not migrate historical v1.x documents into the new PRD/FSD/TDD format.
- Versions after v2.0 can start using the new PRD/FSD/TDD document format and new AIT capability as the normal dogfood flow.

### 验收标准

- Existing v1.x PRD/impl/task commands and tests continue to work.
- v2.0 documents explicitly describe the PRD/FSD/TDD model, template contracts, command surface, codegen context behavior, and merge compatibility.
- AIT can parse and index PRD/FSD/TDD-style chunk ids while still accepting legacy chunk ids.
- AIT can represent PRD/FSD/TDD semantic relationships as specgraph edges.

### 边界与非目标

- v2.0's own PRD and impl do not need to use the new PRD/FSD/TDD format.
- v2.0 does not remove `ait impl` or `ait task`.
- v2.0 does not rewrite historical baseline or merged version documents.

<!-- @id:prd-v2-fsd-tdd-structure-rules -->
## PRD/FSD/TDD structure and graph rules

### 概述

The target document model is a chunk graph:

```text
Version
  -> one PRD
      -> root FSD
          -> recursive child FSD
              -> leaf FSD
                  -> one or more TDD
                      -> each TDD maps to one code file
```

Files are physical containers. Chunks are the semantic unit. Relationships are chunk-to-chunk specgraph edges.

### 业务规则

- Each version in the new model has exactly one PRD.
- Every PRD/FSD/TDD file must have a root chunk.
- The root chunk represents the whole file and carries common file-level context.
- The root chunk does not replace internal semantic chunks.
- A file may contain internal chunks for requirement items, split items, or implementation detail blocks.
- PRD root chunk maps to the root FSD root chunk with `decomposes`.
- Parent PRD/FSD files describe downstream FSD/TDD parts through internal split chunks.
- Parent-child edges are emitted from the parent internal split chunk, except for the PRD root to root FSD case.
- `decomposes` is used for PRD/FSD to FSD relationships.
- `details` is used for FSD to TDD relationships.
- `depends_on` is used only between sibling internal split chunks inside the same parent FSD file.
- FSD files may recursively decompose into child FSD files.
- A leaf FSD may detail one or more TDD files.
- One FSD node must not mix child FSD and TDD children.
- If a lower-level FSD needs a dependency owned by a parent sibling, the dependency must be lifted to the parent split level.
- Infrastructure capabilities such as database, Redis, and message queue are modeled as normal FSD parts.

Naming rules:

- File name equals root chunk id plus `.md`.
- File name and root chunk id use `[PRD]`, `[FSD]`, or `[TDD]` prefixes.
- `_` joins words inside one semantic name.
- `-` joins hierarchy levels.
- Internal split chunk id uses `<parent_root_chunk_id>:<internal_split_chunk_name>`.
- Internal split chunk id must not use literal `:split` as a fixed suffix.
- AIT must not infer semantic relationships from chunk id or file name strings.
- Normal AIT usage must create specgraph relationships explicitly when documents are generated.

### 验收标准

- A validator can detect invalid edge types and invalid graph structures.
- A validator can reject FSD nodes that mix FSD children and TDD children.
- A validator can reject `depends_on` edges that do not connect sibling internal split chunks.
- A validator can reject `depends_on` edges that point directly to downstream root chunks.
- A validator can reject parent-child edges emitted from the wrong source chunk.
- Demo documents can represent infrastructure as ordinary FSD capability and dependency.

### 边界与非目标

- v2.0 does not introduce file-level graph edges.
- v2.0 does not introduce additional trace relation types beyond `decomposes`, `details`, and `depends_on`.
- v2.0 does not decide FSD split depth automatically.

<!-- @id:prd-v2-prd-fsd-tdd-template-contracts -->
## PRD/FSD/TDD template contracts

### 概述

The new PRD/FSD/TDD model needs concrete markdown templates that humans can audit and AIT can later generate. These templates are part of the v2.0 requirement, not optional supporting notes.

The target template files are:

- `TEMPLATE-PRD-AIT-DRAFT.md`
- `TEMPLATE-FSD-AIT-DRAFT.md`
- `TEMPLATE-TDD-AIT-DRAFT.md`

### 业务规则

PRD template:

- Root chunk id uses `<!-- @id:[PRD]-{semantic_name} -->`.
- Internal requirement chunk id uses `<!-- @id:[PRD]-{semantic_name}-{requirement_name} -->`.
- Root chunk includes background and problem, goals and measurement, scope, users and roles, assumptions and constraints, and overall acceptance criteria.
- Requirement chunks include user story, requirement description, business rules, user-visible flow, exception scenarios, acceptance criteria, and open questions.
- PRD writes why and what, not module decomposition, technical design, or target code files.

FSD template:

- Root chunk id uses `<!-- @id:[FSD]-{semantic_name} -->`.
- Internal split chunk id uses `<!-- @id:[FSD]-{semantic_name}:{split_name} -->`.
- Root chunk includes functional scope, feature overview, common business rules, common definitions, interaction contract overview, data model contract, and non-functional requirements.
- Split chunks include functional description, boundary, business flow, business rules, provided interaction contracts, input/output fields, failure codes or exceptions, call constraints, and data contracts.
- FSD template content defines interaction fields and interaction methods, but dependencies are expressed through specgraph instead of ordinary prose management fields.

TDD template:

- Root chunk id uses `<!-- @id:[TDD]-{semantic_name} -->`.
- TDD root chunk includes a YAML-style `target_file: path/to/target_file.ext` declaration.
- TDD root chunk includes technology stack, implementation constraints, file responsibility, code structure, core logic, key data structures, algorithms and flow, error handling, boundary conditions, and unit test requirements.
- Optional internal implementation detail chunk id uses `<!-- @id:[TDD]-{semantic_name}-{detail_name} -->`.
- Unit test requirements must include test file path, framework, normal path, boundary conditions, error path, mocks/fixtures, independent run command, passing standards, and failing conditions.
- Each TDD maps to exactly one target code file.

Template exclusion rules:

- Templates must not include AIT-managed fields such as document state, change log, version metadata, hierarchy type fields, manual downstream-link fields, manual linked-FSD/TDD fields, or specgraph hint fields.
- Templates must not reintroduce task as a document layer.
- Relationship creation belongs to AIT-generated refs, metadata, and specgraph update actions.

### 验收标准

- The three template files exist and use `[PRD]`, `[FSD]`, and `[TDD]` root chunk ids.
- The FSD template shows internal split chunk id format with `:<split_name>`.
- The FSD template does not use literal `:split`.
- The TDD template includes `target_file` as markdown source of truth.
- The TDD template includes passing standards and failing conditions for unit tests.
- The templates do not contain AIT-managed relationship or state fields.

### 边界与非目标

- v2.0 templates are target-format templates for later versions, not the required format of v2.0's own PRD/impl files.
- v2.0 does not require templates to contain concrete downstream specgraph edges.
- v2.0 does not require PRD internal requirement chunks to map one-to-one to implementation chunks.

<!-- @id:prd-v2-fsd-tdd-commands -->
## Parallel FSD, TDD, and codegen commands

### 概述

Users need first-class commands to create and manage FSD and TDD documents without overloading the old impl/task concepts. The new commands should coexist with the existing workflow so v1.x projects remain usable while v2.x projects can start adopting the new model.

### 业务规则

- `ait fsd` manages FSD documents and FSD decomposition.
- `ait tdd` manages TDD documents and target file implementation instructions.
- `ait codegen` prepares code generation context from a TDD root chunk.
- New commands must write version-side files under `versions/<version>/fsd` and `versions/<version>/tdd` for new-model work.
- New commands must create chunk records in version chunks-index.
- New commands must create or update specgraph edges explicitly as documents are generated.
- New commands must not remove or change the behavior of `ait prd`, `ait impl`, or `ait task`.

### 验收标准

- CLI help exposes `fsd`, `tdd`, and `codegen` command groups.
- FSD command flow can create or update an FSD markdown file with a root chunk and internal split chunks.
- TDD command flow can create or update a TDD markdown file with a root chunk and target file declaration.
- Codegen command flow accepts a TDD root chunk id and returns a focused context bundle.
- Existing end-to-end PRD/impl/task tests continue to pass.

### 边界与非目标

- v2.0 does not remove the existing task YAML implementation.
- v2.0 does not require old impl documents to be rewritten as TDD documents.
- v2.0 does not execute AI code generation directly inside the CLI unless an existing AIT pattern already supports that safely.

<!-- @id:prd-v2-codegen-tdd-context -->
## TDD-based code generation context

### 概述

The target model removes task as the new code generation unit. A TDD root chunk represents the implementation instruction for one concrete target code file. The code generation context must be assembled by traversing chunk-level relationships from that TDD root.

### 业务规则

- Each TDD maps to exactly one target code file.
- TDD markdown must specify `target_file`; metadata may redundantly index it, but markdown is the source of truth.
- TDD must include unit test requirements with passing and failing conditions.
- TDD context assembly starts from the TDD root chunk.
- Context assembly includes the TDD file's internal implementation chunks.
- Context assembly recursively collects upstream FSD and PRD chunks needed to understand requirements and functional contracts.
- Context assembly follows the parent internal split chunk to find sibling `depends_on` edges.
- Dependency context is collected through sibling split chunks and their downstream root chunks.
- TDD context assembly must not infer dependencies from names.

### 验收标准

- Given a valid TDD root chunk, `ait codegen` returns the target file path.
- Given a valid TDD root chunk, `ait codegen` returns the TDD root and internal implementation chunks.
- Given a valid TDD root chunk, `ait codegen` returns relevant upstream FSD/PRD chunks.
- Given sibling `depends_on` relationships, `ait codegen` includes dependency contracts required by the target TDD.
- Unit tests cover at least one multi-level FSD to TDD context traversal.

### 边界与非目标

- v2.0 does not require the CLI to edit source code directly.
- v2.0 does not make task YAML the source of truth for new-model code generation.
- v2.0 does not allow one TDD to target multiple code files.

<!-- @id:prd-v2-version-merge-compatibility -->
## Version and merge compatibility

### 概述

AIT must continue to provide versioned document development and baseline merge. The new PRD/FSD/TDD model should participate in the same chunk-level add/modify/delete lifecycle without breaking existing historical data.

### 业务规则

- New PRD/FSD/TDD files in a version are not one-off drafts.
- After confirm and merge, new-model documents must update the global baseline current state.
- Merge must remain chunk-based.
- chunks-index and specgraph must be rebuilt or updated after merge.
- v1.x PRD baseline single-file behavior must not accidentally swallow FSD/TDD files.
- New-model PRD/FSD/TDD baseline files should preserve their intended file containers.
- Backward compatibility must allow old baseline chunks and new-model chunks to coexist.

### 验收标准

- Version merge can promote FSD and TDD chunks into baseline docs without forcing them into `docs/prd/global.md`.
- Version merge can preserve specgraph edges for `decomposes`, `details`, and `depends_on`.
- Legacy confirm behavior still passes existing tests.
- New tests cover merge of at least one FSD file and one TDD file.
- New tests cover mixed legacy baseline data and new-model version data.

### 边界与非目标

- v2.0 does not rewrite historical `.meta` files except through normal version operations.
- v2.0 does not delete old task metadata.
- v2.0 does not require all projects to switch to new-model confirm rules immediately.

<!-- @id:prd-v21-new-model-prd-command -->
## 新模型 PRD 命令入口

### 概述

v2.0 引入了 PRD/FSD/TDD 并行模型，并提供了 `ait fsd`、`ait tdd`、`ait codegen` 命令，但**新模型 PRD 没有创建入口**：`new_model_manager` 只有 `create_fsd`/`create_tdd`，没有 `create_prd`。现状下要产出一个 `[PRD]-` 前缀的新模型 PRD 根文档，只能裸写文件，无法走 CLI。这是后续用新模型重建 project-docs baseline 的第一个阻塞点。

### 业务规则

- 提供创建新模型 PRD 文档的 CLI 能力，产出带 `[PRD]-` 前缀根 chunk 的 PRD markdown。
- 新模型 PRD 文件写入版本工作区 `versions/<version>/prd/`，与现有版本侧写入方式一致。
- 新模型 PRD chunk 注册进版本 chunks-index。
- 创建命令必须与现有旧模型 `ait prd` 行为兼容，不破坏 `prd-` 前缀的旧流程。
- 关系边（如 PRD 根 `decomposes` 根 FSD）按新模型规则显式建立，不从命名推断。

### 验收标准

- 能通过 CLI 创建一个 `[PRD]-{name}` 根 chunk 的新模型 PRD 文件。
- 创建后该 chunk 出现在版本 chunks-index 中。
- 旧模型 `prd-` 前缀的创建/确认/提交流程与现有测试继续通过。
- 新增测试覆盖新模型 PRD 创建路径。

### 边界与非目标

- v2.1 不要求迁移历史 v1.x PRD 文档到新格式。
- v2.1 不移除旧模型 `ait prd` 命令。
- v2.1 不在本需求内完成 project-docs 重建本身。

<!-- @id:prd-v21-new-model-init-scaffold -->
## init 搭建新模型骨架

### 概述

`ait init` 当前只 bootstrap 旧模型基线（`docs/global/*` + 旧 `docs/prd`/`docs/impl`），不产出 PRD/FSD/TDD 的目录与根文档。要让未来的项目（包括 AIT 自身重建后的 project-docs）从新模型起步，init 需要一条显式的新模型初始化路径。

### 业务规则

- `ait init` 提供一条显式的新模型初始化方式，不静默改变旧项目的现有行为。
- 新模型初始化创建 `docs/prd`、`docs/fsd`、`docs/tdd` 三个基线目录。
- 新模型初始化至少产出一个 `[PRD]-` 根 PRD 文档和一个 `[FSD]-` 根 FSD 文档。
- PRD 根 chunk 通过 specgraph 的 `decomposes` 关系指向根 FSD 根 chunk。
- 初始化产物可被现有 chunks-index 与 specgraph 流程重建索引。
- 初始化产物能通过新模型图校验（`specgraph validate-new-model`）。
- 旧模型 init 行为保留为兼容路径，供既有旧项目使用。
- 命令输出报告所采用的 init 模式、创建的文件清单与校验状态。

### 验收标准

- 新项目能显式运行新模型 init，得到 `docs/prd`、`docs/fsd`、`docs/tdd` 目录。
- 生成的 PRD/FSD 文件使用 `[PRD]`/`[FSD]` 根 chunk id。
- 生成的 baseline specgraph 含一条 PRD 根 → 根 FSD 的 `decomposes` 边。
- init 后运行 `ait reindex` 保留生成的 chunk 与图信息。
- `ait specgraph validate-new-model` 在初始化产物上通过。
- 旧模型 init 的现有测试继续通过；新增测试覆盖新模型 init 全新与增量补全两种情形。

### 边界与非目标

- v2.1 不要求把旧模型基线自动转换为新模型基线。
- v2.1 不在 init 内决定具体项目的最终模块分解。
- v2.1 不执行 project-docs 目录切换。

<!-- @id:prd-v21-taskless-confirm -->
## 无 task 的版本合并

### 概述

新模型用 TDD 作为代码生成单元，取代了旧模型的 task YAML。但 `version confirm` 的前置守卫历史上围绕"所有 task 必须 done"设计。新模型版本（只有 PRD/FSD/TDD、零 task）能否正确走完 confirm → merge → git commit，目前没有端到端验证，是新模型生命周期闭环的关键未知。

### 业务规则

- 新模型版本（无 task）能正常通过 `version confirm` 前置守卫。
- confirm 把新模型 PRD/FSD/TDD chunk 按 chunk 维度合并进 baseline。
- 合并保留 `decomposes`/`details`/`depends_on` 三种关系到 baseline specgraph。
- 合并后 chunks-index 与 specgraph 被重建或更新。
- 旧模型「task 必须 done」的守卫对旧模型版本保持不变。

### 验收标准

- 一个只含 PRD/FSD/TDD、无 task 的版本能成功 `version confirm`。
- confirm 后 FSD/TDD chunk 进入 baseline，且未被塞进 `docs/prd/global.md`。
- confirm 后 baseline specgraph 保留三种新模型关系边。
- 新增测试覆盖 taskless confirm 路径。
- 旧模型 confirm 的现有测试继续通过。

### 边界与非目标

- v2.1 不删除 task 元数据，不改写历史已合并版本。
- v2.1 不强制所有项目立即切换到新模型 confirm 规则。

<!-- @id:prd-v21-target-file-uniqueness -->
## target_file 唯一性校验

### 概述

新模型要求每个 TDD 唯一映射一个 `target_file`（代码文件）。这正是"多人协作不撞同一文件"（目标 2）的硬保证基础。但当前 validator 只校验图结构，不校验是否有两个 TDD 声明了同一个 `target_file`，导致该保证仅靠拆分自觉，未被工具强制。

### 业务规则

- 校验同一范围内（版本内 / baseline 内）不同 TDD 不得声明同一 `target_file`。
- 发现重复时报错，错误码为 `DUPLICATE_TARGET_FILE`，并列出冲突的 TDD chunk id 与 target_file。
- 校验以 TDD markdown 中的 `target_file` 为准（markdown 是 source of truth）。
- 该校验集成进新模型校验路径（`specgraph validate-new-model`），与旧模型格式校验分离。

### 验收标准

- 两个 TDD 指向同一 `target_file` 时，校验报错 `DUPLICATE_TARGET_FILE` 并列出冲突项。
- 每个 TDD 指向不同文件时，校验通过。
- 校验返回机器可读 JSON，含冲突 chunk id、target_file。
- 新增测试覆盖重复与不重复两种情形。

### 边界与非目标

- v2.1 不引入文件级 specgraph 图边（仍以 TDD→target_file 字段为准）。
- v2.1 不自动重写或修复冲突的 target_file。
- v2.1 不校验 target_file 指向的物理文件是否真实存在。

<!-- @id:prd-v22-new-model-version-commit -->
## 新模型版本提交

### 概述

新模型用 `fsd/tdd/prdv2 create` 把 chunk 注册进版本工作区，但注册态是 `working`。`version confirm` 只合并 `committed` 态 chunk，导致新模型版本 confirm 时报 `MERGE_NO_COMMITTED`（无可合并 chunk）。旧模型靠 `prd commit`/`impl commit` 把 chunk 推进到 committed，新模型缺少对应的提交/锁定入口。这是新模型 create→commit→confirm 生命周期断裂的核心缺口。

### 业务规则

- 提供一个新模型版本提交入口，把该版本所有 `working` 态 chunk 一次性推进到 `committed`。
- 提交后这些 chunk 在本版本内锁定，与旧模型 commit 语义一致（不可再改，要改走 version reset）。
- 提交是 taskless 流程的一部分：新模型不拆 task，提交即"准备好被 confirm 合并"。
- 提交入口与旧模型 `prd/impl commit` 并存，不改其行为。
- 提交后 `version confirm` 能正常合并这些 chunk 进 baseline。

### 验收标准

- [ ] 新模型版本（含 fsd/tdd/prdv2 chunk）执行提交后，chunk 全部变 committed。
- [ ] 提交后 `version confirm` 成功合并，不再报 `MERGE_NO_COMMITTED`。
- [ ] 提交后再次改动被拒（锁定生效）。
- [ ] 旧模型 `prd/impl commit` 现有测试继续通过。
- [ ] 新增测试覆盖新模型 create→提交→confirm 全链路。

### 边界与非目标

- 不为新模型引入 task 层。
- 不改旧模型 commit 的逐 chunk 语义。
- 不在本需求内做 codegen 或 init 相关改动。

<!-- @id:prd-v22-new-model-version-ensure -->
## 新模型版本元数据自动创建

### 概述

新模型 `fsd/tdd/prdv2 create` 通过 `write_version_file` 写文件时会建出版本目录，但不创建版本元数据（`.meta/versions/<v>.yaml`）与版本索引。结果是版本处于"有目录、无 meta"的半建状态，`version confirm` 报 `Version <v> has no metadata file`。旧模型靠 `prd create` 顺带建版本 meta，新模型路径缺这一步。

### 业务规则

- 新模型 create 在写文件前，确保目标版本的 meta 与索引存在；缺失则创建，已存在则不动（幂等）。
- 自动创建容忍版本目录已存在（不与现有 create 的"目录已存在即报错"冲突）。
- 版本号取自命令显式传入的 `--version`，不隐式臆测命名。
- 不改旧模型版本创建路径。

### 验收标准

- [ ] 对一个尚无 meta 的版本执行新模型 create 后，`.meta/versions/<v>.yaml` 与版本索引存在。
- [ ] 同版本重复 create 不报"已存在"错误（幂等）。
- [ ] 新模型版本随后可正常 `version confirm`。
- [ ] 旧模型版本创建的现有测试继续通过。

### 边界与非目标

- 不改旧模型 `prd create` 的自动建版本逻辑。
- 不引入新的版本号自动分配策略。

<!-- @id:prd-v22-codegen-baseline-fallback -->
## codegen 基线回退

### 概述

`codegen prepare <tdd>` 在未显式传 `--version` 且无活动未合并版本时，因 `versions.current()` 返回 None 而报 `NO_VERSION`。但 baseline 中已合并的 TDD 本应能直接出代码生成上下文——这正是迭代时"从已建基线追溯到代码文件"（目标 1）的常用场景。codegen 应在无活动版本时回退到 baseline 解析。

### 业务规则

- `codegen prepare` 未指定版本且无活动版本时，从 baseline 解析 TDD 根 chunk 与上游/依赖上下文。
- 有活动版本时维持现有行为（版本优先、回退 baseline）。
- 回退路径仍返回 `target_file` 与上游 FSD/PRD、依赖契约。

### 验收标准

- [ ] 已合并 baseline 后、无活动版本时，`codegen prepare <baseline-tdd>` 成功返回 target_file 与上游上下文。
- [ ] 有活动版本时行为不变，现有 codegen 测试继续通过。
- [ ] 新增测试覆盖无活动版本的 baseline 回退。

### 边界与非目标

- 不改 codegen 的上下文组装算法（上游遍历、依赖收集不变）。
- 不引入反向（代码→spec）查询。
