<!-- @id:[PRD]-ait -->
<!-- @ref:fsd/[FSD]-ait#[FSD]-ait rel:decomposes -->
## ait 产品 PRD

### 概述

AIT 是面向 AI 协作的"类 Git"文档版本管理工具，服务 vibe coding 下 PRD/设计文档的协作与版本管理，打包为开源 Claude Code Skill。解决传统 Git 三不足：不够细粒度（chunk 级 vs 行级）、不够语义化（spec↔代码关联）、不够 AI 友好（聚焦上下文组装）。

### 范围

In scope：chunk 级三态版本控制与原子版本；旧 `prd→impl→task→code` 流水线；并行 `prd→fsd→tdd→code` 新模型；spec→代码追溯；FSD 分区支持并行开发。Out of scope：多人实时协作锁；反向 code→spec 与需求级（PRD 子条目→FSD）追溯；非 markdown 文档。

### 需求：chunk 级文档版本控制

以 `<!-- @id -->` chunk 为单位版本化：三态 working→staged→committed，commit 即锁定本版本不可改；版本为原子单元，要么整体 confirm 合入基线、要么 `version reset` 整版重来，无局部撤销；baseline 与 per-version 索引/specgraph 分文件。验收：三态流转与锁定生效；confirm 原子合并失败回退；reset 物理清空。

### 需求：双流水线（旧 prd/impl/task + 新 prd/fsd/tdd）

旧模型：PRD（需求）→ impl（实现设计，含 @extract 动态 global）→ task（AI 编码单元）→ code。新模型：PRD → 递归 FSD（功能分解树）→ 叶 FSD `details` TDD（一文件一映射）→ codegen → code。两模型并存；新模型 PRD 命令取名 `prd`、旧模型 PRD 命令更名 `prdv1`，其余旧命令不变；新模型用 prd/fsd/tdd/codegen。验收：两条流水线分别可端到端跑通。

### 需求：可追溯——spec→代码（目标 1）

每个叶 TDD 唯一映射一个 `target_file`；`codegen prepare <tdd>` 沿 specgraph 上溯 FSD/PRD、旁取依赖契约，输出聚焦代码生成上下文（含 target_file）；无活动版本时从 baseline 解析。验收：codegen 能从任一叶 TDD 解析出 target_file 与上游/依赖上下文。

### 需求：可拆分——并行不冲突（目标 2）

FSD 递归分解把系统拆成互不重叠功能子树，不同人领不同子树；每个 TDD 唯一映射一个 target_file，`validate-new-model` 强制 target_file 全局唯一（重复报 `DUPLICATE_TARGET_FILE`）；关系仅三种 `decomposes`/`details`/`depends_on`，不从命名推断，必须显式建边。验收：重复 target_file 被拦截；FSD 图结构合法性校验通过。

### 用户与角色

- **AI 协作开发者（主）**：用 AIT 在 vibe coding 下管理 PRD/FSD/TDD、驱动 codegen、迭代代码。高频，读写。
- **维护者**：用追溯(目标1)定位待改代码、用 FSD 分区(目标2)分配并行工作。中频。
- **AI agent（Claude）**：经 SKILL.md 路由调 CLI，按 JSON 契约消费输出。

### 目标与度量

- 追溯：从任一 spec 节点 1 跳 codegen 拿到 target_file + 上下文（目标1）。
- 隔离：FSD 分区使不同人/agent 落不同文件，0 文件冲突（target_file 唯一性强制，目标2）。
- 原子：版本 confirm 全有或全无，失败可回退。
- 自包含：skill 安装到任意项目即可用，0 对 AIT 自身 project-docs 的运行依赖。

### 依赖与风险

- 依赖：Python 3.10+ / pydantic / PyYAML / click / git。
- 风险：跨域模块依赖只能在域 split 层用 depends_on 表达（同父约束）→ codegen 依赖上下文需向域层收集（后续增强）。
- 边界：不做多用户实时协作锁、不做反向 code→spec、非 markdown 文档不纳管。
