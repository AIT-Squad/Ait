# AIT — 类 Git 的 AI Coding 文档管理工具

> 一个（in-develop 的）Claude Code Skill：为**大型项目的持续迭代**与**多人协作的 AI 开发**而生，
> 目标是让"AI 参与开发的项目"在长跑中保持可维护性。

**这是一个 Skill，不是直接手敲的 CLI。** 安装后，一切操作都在 Claude Code 里以斜杠命令发起：
`/ait init`、`/ait prd create`、`/ait version merge`……你的 PATH 里不存在全局 `ait` 二进制——
路由机制见 [USER_GUIDE.zh-CN.md §1.2](USER_GUIDE.zh-CN.md)。

---

## Why

AI 实现 MVP 的能力已经很强，但在迭代版本的过程中，多多少少都会遇到被 AI 改崩的情况：
比如 AI 忘记了之前的某个约束，又或是修改某个模块时忘记了它对其他依赖模块的影响。

一个持续迭代的生产级项目，通常面临的是各种特殊业务诉求、特殊实现约束。这类信息不断
增加的情况下，模型在修改某个问题时，注意力会被项目中大量的其他信息分散。

这类约束和背景知识，应该在**项目范围内被固化并持续更新**，而不是散落在聊天记录和个人
记忆里。AI 在处理某个问题时，需要的是"与这个问题有关的一切"，而不是"这个项目的一切"。

## How

在修改一个问题时，应该给模型提供**与这个问题相关的上下文信息，屏蔽掉其他信息**——把模型
注意力的甜点区间全部用在当前这个问题上。

所以 AIT 用一套**结构化的文档体系**把开发用的约束（prompt）组织起来，并且在真正进行代码
生成的时候，能够精确提取出与当前任务相关的信息：

- **chunk 级版本控制**（类 Git）：文档以 `<!-- @id:xxx -->` 标注的语义 chunk 为最小单元，
  有 `/ait version create / commit / confirm / merge / revert` 的完整版本生命周期；merge 原子
  落盘，失败字节级回退。
- **显式关系图谱（SpecGraph）**：chunk 之间的派生/分解/细化/依赖关系是图上的显式边，
  不靠命名推断、不写在正文里。改某个东西时，`/ait deps` / `/ait impact` 能回答"它依赖谁、影响谁"。
- **强制不变式**：PRD↔FSD 唯一映射、每个 TDD 唯一对应一个目标文件、无孤儿、无断链、
  可追溯无环——写时门禁零落盘拒绝，合入前全局校验。
- **聚焦上下文组装**：`/ait codegen prepare` 沿图谱上溯，只打包"这个 TDD 的实现蓝图 + 上游
  约束链 + 依赖方的接口契约 + 目标文件现状"，不多不少。

## 三级文档体系

```
[PRD] 产品需求文档 ──derives──▶ [FSD] 功能规格文档 ──decomposes──▶ 功能树（递归拆分）
        what / why                    功能分解 + 能力契约（黑盒接口）
                                          │
                                      ──details──▶ [TDD] 技术设计文档
                                          单文件实现蓝图（白盒，1 TDD ↔ 1 target_file）
```

| 层级 | 回答 | 内容 |
|---|---|---|
| **PRD** (Product Requirements Doc) | what / why | 用户视角的需求，零技术内容；每条需求带用户故事 + 验收标准 |
| **FSD** (Functional Specifications Doc) | 怎么拆 | 功能分解结构 + 对外能力契约（只写"提供什么"，不写实现） |
| **TDD** (Tech Design Doc) | 怎么实现 | 单文件实现蓝图；每个 TDD 唯一映射一个 `target_file` |

代码生成时，AI 拿到的不是整个文档库，而是沿关系图谱组装出的、刚好够写这一个文件的
上下文 bundle。

## 一张图看全流程

![AIT 命令流转全景：文件为节点，/ait 命令为边；红色虚线为返工路径；右侧为版本迭代回路](docs/ait-pipeline.svg)

文件为节点、命令为边：每一层 `create` 落下对应文档，`codegen prepare` 把 TDD 与代码文件
连接起来，`version commit → confirm → merge` 把版本工作区原子合入 baseline；红色虚线是
各层返工路径，右侧回路是版本不断迭代（v0.1 → v0.2 → …）。

## Q&A

**Q: 与 AGENTS.md / MEMORY.md 这类 agent 记忆文件有什么区别？**

AGENTS.md / MEMORY.md 等记忆文件分项目级和用户级，其中有一些是用户习惯、个人偏好，
不应该作为项目全局的长期约束。而有一部分约束——业务规则、架构决策、接口契约——应该
作为项目全局的长期约束，**共享给项目中的所有协作者（人和 AI），全局保持一致、可评审、
可回溯**。AIT 管的是后者：它有版本、有验收、有不变式门禁，记忆文件管不了这些。

**Q: 与 superpowers / gsd 这类 skill 有什么区别？**

这类 skill 关注"如何完成一个开发任务"（流程编排、任务执行）。AIT 更关注**规范化地保持
整个项目的全局记忆**——让第一千次迭代和第一次迭代一样可靠。两者不冲突：任务执行类
skill 解决"这一次怎么做好"，AIT 解决"长期怎么做不坏"。

**Q: 与 Git 是什么关系？**

互补。Git 以文件为单位、以行为 diff 单元，管代码；AIT 以语义 chunk 为单位，管**驱动
AI 编码的设计文档**及其关系。AIT 管理的 `project-docs/` 本身就是独立 git 仓，每次 merge
还会记录文档版本与代码版本的绑定（哪个 commit 的代码对应哪版规格）。

**Q: 什么场景不适合用 AIT？**

做一个 MVP、一个小功能、一次性脚本——AIT 太重了，直接用 AI 写就好。AIT 的价值在
**持续开发的规模化项目**：迭代次数多、约束累积多、多人多 AI 协作、改一处要顾及全局
的场景。项目越长寿，AIT 的价值越大。

---

## 现状与文档

AIT 自身就是用 AIT 开发的（dogfooding）：`project-docs/` 是它的权威设计源，每个版本都走
完整的 `/ait version create → prd → fsd → tdd → codegen → confirm → merge` 闭环。

| 文档 | 内容 |
|---|---|
| [USER_GUIDE.zh-CN.md](USER_GUIDE.zh-CN.md)（[English](USER_GUIDE.md)） | 任务导向的操作手册与排错 |
| [DESIGN.md](DESIGN.md) | 架构设计、设计取舍、模块地图 |
| [CHANGELOG.md](CHANGELOG.md) | 版本演进史 |
| [skill/ait/SKILL.md](skill/ait/SKILL.md) | Skill 命令契约 |

MIT licensed.
