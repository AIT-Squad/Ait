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
