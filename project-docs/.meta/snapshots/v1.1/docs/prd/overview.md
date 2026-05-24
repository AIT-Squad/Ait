# 系统概览

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
/ait:prd <title>          → AI 三阶段讨论 PRD → 写入版本工作区
/ait:prd commit           → 提交 PRD 到 committed
/ait:impl <block-id>      → AI 基于 PRD 生成 impl
/ait:impl commit          → 提交 impl
/ait:version merge        → 合并到基线 docs/
```

MVP 不包含：代码生成、反向同步、多人协作、AI 改 block、IDE 跳转编辑、list、reindex。

<!-- @id:prd-overview-roadmap -->
## 路线图

| 版本 | 范围 | 状态 |
|------|------|------|
| V1（MVP） | 7 个核心命令 + 单机闭环 + Claude Code Skill 形态 | 开发中 |
| V1.1 | `list`/`edit`/`reindex` + 跨 AI IDE 适配（Cursor / Continue / Cline） | 规划 |
| V2 | 多人协作（基于 Git）+ `/ait:impl code` 代码生成 + sync-status 双向同步 | 规划 |

每个版本结束以"合入基线"为分界。

<!-- @id:prd-overview-terminology -->
## 核心术语

| 术语 | 定义 |
|------|------|
| Block | 由 `<!-- @id:xxx -->` 标注的最小版本控制单元 |
| 基线（baseline） | `docs/` 目录，所有版本合并后的真实状态 |
| 版本（version） | `versions/{vX.Y}/` 下的增量工作区 |
| 三阶段 | working → staged → committed |
| @ref | 跨 Block 引用，形如 `<!-- @ref:file#block-id rel:type -->` |
| L1~L4 | AI 上下文的四层模型 |
| Skill | Claude Code 等 AI IDE 的可加载能力包，包含 SKILL.md + 脚本 |

<!-- @id:prd-overview-design-principles -->
## 设计原则

1. **内容与元数据分离**：markdown 只放内容 + `@id`/`@ref`，所有状态/版本信息在 `.meta/` 的 YAML 中
2. **块级原子**：合并的最小单位是块，不做行级 diff
3. **AI 友好**：所有命令的输出是结构化 JSON，便于 AI 消费；所有命令的设计避开"魔法"，让 AI 能准确预测系统行为
4. **跨 IDE 中立**：核心是纯 CLI（Python），各 AI IDE 通过自己的 Skill/Rule 机制包装
5. **可追溯**：每次 commit 产生 `chg-{id}.yaml`，合并产生快照，任何变更都能回到时间点
