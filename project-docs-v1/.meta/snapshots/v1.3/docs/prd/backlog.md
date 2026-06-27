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
