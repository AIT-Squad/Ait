# AIT — 让 AI 开发从“一次生成”走向持续交付

> AIT 是一个面向持续迭代项目的 Claude Code Skill。它把需求、功能设计和技术设计拆成可追踪的语义 chunk，维持 AI 开发上下文的长期完整性，只把当前任务相关的可信规格交给 AI，并用阶段门禁、依赖校验和制品验收约束每次迭代。

AIT 适合这样的团队：项目会长期演进，业务约束越来越多，多名开发者或多个 AI 需要基于同一套需求和设计协作。

**AIT 不是新的代码仓库，也不替代 Git、代码评审或项目管理工具。** 它位于这些工具之前，负责把“要做什么、如何拆分、每个文件如何实现”沉淀为团队共享、可版本化的规格。

English: [README.md](README.md)

## 先理解三个概念

AIT 用三类文档把一个需求逐层拆成可以独立交付的开发任务：

- **PRD（Product Requirements Document，产品需求文档）**：从用户和业务视角说明为什么做、为谁做、要解决什么问题，以及如何判断需求完成。
- **FSD（Functional Specification Document，功能规格文档）**：把 PRD 拆成功能域，定义每块功能提供什么能力、与其他功能如何协作，是团队进行功能分工的主要边界。
- **TDD（Technical Design Document，技术设计文档）**：把叶子功能进一步细化为单文件实现蓝图，说明一个 `target_file` 应该如何实现和测试。这里的 TDD 指技术设计文档，不是 Test-Driven Development（测试驱动开发）。

它们分别回答：**做什么和为什么做 → 功能如何拆分 → 一个文件如何实现**。

---

## AIT 解决什么问题？

### 1. 降低上下文腐化，让 AI 基于长期可信的上下文工作

项目长期迭代后，上下文不只是变多，还会逐渐腐化：需求和决策散落在聊天记录里，旧文档与新实现不一致，新旧约束互相冲突，不同成员和 AI 持有不同版本的项目认知。此时，即使模型拥有更大的上下文窗口，也可能基于过期、矛盾或无关的信息做出错误修改。

AIT 的首要目标不是让 AI “记住整个项目”，而是维持项目上下文的长期完整性：

- **固化可信来源**：将 PRD、FSD、TDD 从临时对话沉淀为可版本化、可评审的项目规格；
- **控制腐化进入基线**：用上下文回执、阶段冻结、依赖关系和合入门禁发现过期背景、断链与结构冲突；
- **按任务投递上下文**：将规格拆成带稳定 ID 的语义 chunk，并通过 SpecGraph 选择当前任务真正相关的内容。

执行某个 TDD 时，AIT 只组装：

- 当前文件的技术设计；
- 上游 FSD 和 PRD 约束；
- 直接依赖模块的能力契约；
- 目标文件的当前内容。

因此，提高 AI 聚焦度和减少无关 token 是控制上下文腐化带来的直接收益，而不是最终目的。实际 token 数仍取决于 chunk 大小和依赖链；AIT 当前不提供硬 token 预算或自动裁剪保证。AIT 也不能证明规格的业务含义一定正确——错误需求或遗漏关系仍需通过团队评审发现。

### 2. 把 AI 开发任务拆成团队可分工的边界

AIT 使用三层规格把一次需求逐步拆小：

```text
PRD：团队对齐“为什么做、用户看到什么”
  ↓
FSD：拆成功能域、能力契约和依赖关系
  ↓
TDD：拆成单文件实现任务（1 个 TDD 对应 1 个 target_file）
  ↓
codegen：为每个文件准备独立上下文并驱动 AI 编码
```

FSD 可以继续递归分解；TDD 的 `target_file` 必须唯一。这些约束让团队可以按功能域、再按目标文件分派任务，减少多人或多个 AI 同时修改同一文件的概率。

AIT 当前采用**单活动版本、单工作区写者**模型：它不创建 Git 分支、不合并 PR、不提供多人写锁，也不记录谁批准了 PRD。团队评审和人员委派由外部流程完成；FSD、TDD 可以由多人并行提出设计方案，但推荐由一名集成者在同一个 AIT 工作区中串行写入和确认。TDD 确认后，代码实现再进入外部 Git 分支或 worktree 并行开发。

### 3. 让 AI 项目具备可持续迭代的工程约束

AIT 不只保存文档，还把交付流程变成可检查的状态机：

```text
version create
  → PRD create / confirm
  → FSD create / decompose / confirm
  → TDD create / confirm
  → codegen
  → acceptance
  → version confirm / merge
```

AIT 会在关键节点检查：

- 是否按 PRD → FSD → TDD 的顺序推进；
- 需求、功能和实现是否完整可追踪；
- 是否存在孤儿、断链、非法树环或重复 `target_file`；
- `confirm` 后的合并计划是否已过期；
- 项目自定义的测试、构建或其他验收命令是否通过；
- 规格版本与代码提交是否已建立绑定。

因此，AIT 更适合“持续迭代并需要稳定交付”的项目，而不是一次性生成代码。

---

## 能力与边界

| 你需要的能力 | AIT 能做什么 | 仍需外部工具完成什么 |
|---|---|---|
| 上下文完整性与 AI 聚焦 | 版本化规格，用回执和门禁控制过期/冲突上下文，并按关系图选择当前 TDD 的相关内容 | 源规格的语义正确性、模型 token 上限与成本控制 |
| PRD 团队评审 | 固化用户故事、验收标准并在 `prd confirm` 后冻结 | 评审人、审批记录、会议或 PR 流程 |
| 功能拆分与委派 | 递归拆分 FSD，明确能力契约和依赖 | 人员排期与任务指派 |
| 多分支开发 | 以唯一 `target_file` 形成可独立实现的 TDD | branch/worktree 创建、代码合并与冲突处理 |
| AI 编码 | 为每个 TDD 组装隔离上下文，由 Skill 驱动 AI 实现 | 最终代码评审与人工决策 |
| 生产交付约束 | 阶段门禁、图校验、验收命令、确定性合并计划、版本绑定与回滚锚点 | CI/CD、权限、发布审批与线上运维 |

---

## 推荐的团队协作方式

下面的流程可以落地“整体评审、分层拆分、分支开发、统一收口”，同时符合 AIT 当前的真实边界。

### 阶段 1：团队确认 PRD

1. 产品、设计、研发共同讨论用户故事、范围和验收标准。
2. 一名集成者通过 AIT 写入最终结论。
3. 外部评审通过后执行 `/ait prd confirm`，冻结需求层。

### 阶段 2：按 FSD 分工并行设计

1. PRD 确认后，由集成者使用 `fsd create --parent <PRD-root>` 创建根 FSD，并在其中定义边界清晰的功能 split；需要递归细化的 split 再使用 `fsd decompose <parent-split> <child-FSD-root>` 建立子 FSD。
2. 团队将不同 FSD 分配给不同负责人。各负责人可以并行设计自己负责功能的能力契约、依赖关系和集成验收，并提交设计方案。
3. AIT 当前不提供规格分支管理、多人写锁或版本元数据的语义合并。为避免索引和 SpecGraph 冲突，推荐由集成者在同一个 AIT 工作区中串行写入评审通过的设计，而不是直接合并多人修改的 `project-docs` 分支。
4. 集成者运行 `/ait specgraph validate-new-model` 并审阅关键依赖，整体评审通过后执行 `/ait fsd confirm`。该命令冻结 FSD 层；孤儿、追踪和树环等完整全局不变式由最终的 `/ait version confirm` 统一检查。

### 阶段 3：并行设计 TDD

1. 以已确认的 FSD 为共同输入，将不同叶子 FSD 分配给对应负责人。
2. 各负责人可以并行提出 TDD 方案，明确 `target_file`、文件职责、实现方案和测试要求。
3. 集成者在同一个 AIT 工作区中串行创建并评审 TDD，确认每个 `target_file` 唯一、文件边界没有冲突后执行 `/ait tdd confirm`。

### 阶段 4：按 TDD 并行编码

1. 将已确认的 TDD 分配给不同开发者或 AI，并使用独立 Git 分支或 worktree；每个开发环境都需要能够访问同一已确认版本的 `project-docs`。
2. 每个开发者或 AI 对自己的 TDD 执行 `/ait codegen prepare <TDD-id>`，基于聚焦上下文实现对应文件。
3. 完成代码、测试和代码评审后，通过外部 Git 流程合并各代码分支。

> 多人协作从 FSD split 后开始，但当前可靠流程是“并行提出 FSD 设计 → 集成者串行写入并 `fsd confirm` → 并行提出 TDD 设计 → 集成者串行写入并 `tdd confirm` → 代码分支并行实现”。AIT 的规格写入仍保持单工作区写者。

### 阶段 5：统一验收并收口版本

1. 确保当前宿主代码仓只包含本版本预期改动。
2. 执行验收命令并检查版本状态。
3. 使用 `version confirm` 完成全局门禁和代码提交绑定。
4. 使用 `version merge` 将规格工作区合入基线。
5. 如需发布，先用 `/ait push --dry-run` 预览，再执行 `/ait push`。

> 注意：`version confirm` 通过后可能对宿主仓执行 `git add -A` 并创建制品提交。运行前应清理或提交与当前版本无关的改动。

---

## 快速开始

### 前置条件

- Claude Code；
- Python 3.10 或更高版本；
- Git；
- 首次安装依赖时可访问 Python 包源。

### 1. 安装 Skill

在 AIT 仓库根目录运行：

```bash
python install.py
```

默认安装到 `~/.claude/skills/ait/`。升级时运行：

```bash
python install.py update
```

安装后重启 Claude Code。AIT 是 Skill，不是系统级 CLI；日常使用统一输入 `/ait <subcommand>`。

### 2. 初始化项目

在你的代码仓根目录打开 Claude Code：

```text
/ait init --new-model --name my_project
```

AIT 会创建独立的 `project-docs/` 规格仓。后续命令必须在包含该目录的项目根执行。

### 3. 完成第一个迭代

```text
/ait version create v0.1

/ait prd create "[PRD]-my_project"
# 与 AI 讨论并写入需求
/ait prd confirm

/ait fsd create "[FSD]-my_project"
# 根据需要继续拆分：
/ait fsd decompose "[FSD]-my_project:core" "[FSD]-core"
/ait fsd confirm

/ait tdd create "[TDD]-core" --parent "[FSD]-core:feature"
/ait tdd confirm

/ait codegen prepare "[TDD]-core"

/ait acceptance set "pytest -q"
/ait acceptance run
/ait version commit v0.1
/ait version confirm v0.1 --conflict-policy abort
/ait version merge v0.1
```

`prd/fsd/tdd create` 会先让 Skill 获取相关背景并与用户讨论，再携带上下文回执写入；通常不需要手工编辑 `project-docs/`。请勿绕过 AIT 直接修改其管理的文档或 `.meta` 文件。

---

## 三层规格分别写什么？

| 层级 | 核心问题 | 主要内容 | 评审关注点 |
|---|---|---|---|
| **PRD** | 为什么做、用户得到什么？ | 用户故事、范围、目标、用户级验收标准 | 团队是否对需求达成一致 |
| **FSD** | 功能如何拆、模块提供什么？ | 功能边界、能力契约、依赖和集成验收 | 是否可独立分工、接口是否清楚 |
| **TDD** | 一个文件具体如何实现？ | `target_file`、代码结构、核心逻辑、错误边界、单测要求 | 是否足够让 AI 独立实现该文件 |

---

## 什么时候适合使用 AIT？

**推荐使用：**

- 项目会经历多个版本并长期维护；
- 业务规则、接口约束和历史决策持续累积；
- 多名开发者或多个 AI 需要共享同一套规格；
- 一处修改经常影响多个模块；
- 团队希望把测试、构建等验收变成合入前门禁。

**不推荐使用：**

- 一次性脚本、快速原型或很小的独立功能；
- 团队不准备维护 PRD、FSD 和 TDD；
- 期望工具自动完成 Git 分支管理、PR 审批或 CI/CD；
- 需要多个操作者直接并发写入同一个 AIT 工作区，且不设置统一集成者。

---

## AIT 与 Git、Agent 记忆有什么区别？

- **Git 管代码历史；AIT 管驱动 AI 开发的规格及其关系。** 两者互补，AIT 会记录规格版本与代码提交的绑定。
- **AGENTS.md / MEMORY.md 管通用规则或个人偏好；AIT 管可评审、可验收、可追踪的项目需求和设计。**
- **任务执行 Skill 关注“这次怎么做完”；AIT 关注“项目迭代很多次以后仍不丢约束”。**

---

## 当前状态与进一步阅读

AIT 正在持续开发，并从 v2.0 起使用自身的 PRD → FSD → TDD → codegen 流程迭代。

| 文档 | 适合什么时候读 |
|---|---|
| [USER_GUIDE.zh-CN.md](USER_GUIDE.zh-CN.md) | 准备正式使用、查询完整命令或排错时 |
| [DESIGN.md](DESIGN.md) | 想理解架构、状态机和设计取舍时 |
| [CHANGELOG.md](CHANGELOG.md) | 查看版本演进和最新能力时 |
| [skill/ait/SKILL.md](skill/ait/SKILL.md) | 查看 Skill 路由与命令契约时 |

MIT License.
