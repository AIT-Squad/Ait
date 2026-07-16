<!-- @id:[PRD]-ait -->
## ait 产品 PRD

### 概述

AIT 是面向 AI 协作的"类 Git"文档版本管理与实现编排工具,服务 vibe coding 下 PRD/设计文档到代码的协作与版本管理,打包为开源 Claude Code Skill。它解决传统 Git 的三点不足:不够细粒度(以 `<!-- @id -->` 标注的 chunk 为单位,而非文件/行)、不够语义化(把 PRD↔FSD↔TDD↔代码的关联显式建模)、不够 AI 友好(能沿关系为 codegen 组装聚焦上下文)。核心价值:让 AI 参与的规格与代码始终同源、可门禁、可回退、可追溯。

### 范围

**In scope**:chunk 级三态版本控制与全有或全无的原子版本;新模型主线 `PRD → FSD(递归分解)→ TDD(一文件一映射)→ codegen → 代码`;spec→代码的可追溯;FSD 分区支持并行开发;六不变式的代码级强制;制品验收门禁。**Out of scope**:多人实时协作锁;反向 code→spec 追溯;非 markdown 文档纳管;chunk 级删除与 legacy 流程退役(后续能力)。

### 目标与度量

| 目标 | 衡量方式 | 目标值 |
|---|---|---|
| 可追溯(目标1) | 从任一叶 TDD 经 codegen 拿到 target_file + 上溯全链上下文 | 1 跳可达 |
| 可隔离(目标2) | FSD 分区使不同人/agent 落不同文件 | 0 文件冲突(target_file 唯一性强制) |
| 原子性 | 版本 merge 全有或全无 | 失败字节级可回退 |
| 自包含 | skill 安装到任意项目即可用 | 0 对 AIT 自身 project-docs 的运行依赖 |

### 反向要求

- 不做多用户实时协作锁(单用户本地版本控制)。
- 不做反向 code→spec 追溯(只保证 spec→代码正向可追溯)。
- 不纳管非 markdown 文档。
- 本 PRD 不描述实现细节(实现分解归 FSD、文件级设计归 TDD);不承载 chunk 间关系声明(关系只存于 SpecGraph)。

<!-- @id:[PRD]-ait:chunk_versioning -->
### 需求:chunk 级原子版本控制

**用户故事:** 作为 AI 协作开发者,我希望以 chunk 而非文件/行为单位管理规格版本,并让每个版本作为原子单元合入或整体退出,以便细粒度地演进规格且永不留下半合入的脏状态。

#### 验收标准
1. WHEN 对 chunk 执行三态流转(working→staged→committed)THEN 各态转换生效,committed 后再改报锁定错误。
2. WHEN 版本 merge 的任一步失败 THEN 系统 SHALL 按字节回退 docs 与 .meta,不残留半合入状态,可重试。
3. WHEN 对未合入版本 revert THEN 该版本工作区被物理清空,基线不受影响。
4. baseline 与 per-version 的索引/关系图分文件存储,互不污染。

<!-- @id:[PRD]-ait:mainline_pipeline -->
### 需求:PRD→FSD→TDD→codegen 主线管线

**用户故事:** 作为 AI 协作开发者,我希望从 PRD 出发与 AI 讨论逐层分解为 FSD 功能树、再细化为文件级 TDD、最后由 codegen 驱动编码,以便让需求到代码的每一步都结构化、可门禁。

#### 验收标准
1. WHEN 依次 prd create → fsd create --parent(从 PRD 派生功能树根)→ fsd decompose(功能树向下拆分)→ tdd create --parent(叶子细化)→ codegen prepare THEN 每层文档写入版本工作区,四种关系(派生/拆分/细化/依赖)各自随其创建命令原子出生——派生随 fsd create --parent、拆分随 fsd decompose、细化随 tdd create --parent、依赖随 fsd create 的声明,codegen 输出目标文件的聚焦上下文。
1a. 派生与拆分是两种关系:PRD 与其唯一 FSD 功能树根之间是"派生"(问题到方案的承接,恰一对一);FSD 内部父子之间是"拆分"(整体到部分的分解)。二者语义、基数、校验规则各自独立。
2. WHEN 每层 confirm 后不满意执行 revert THEN 冻结解除、可继续修改,无终态陷阱(门禁配返工)。
3. IF 关系申报违反基数或引用不存在的 chunk THEN 拒于落盘之前且零残留,修正后可重试。

<!-- @id:[PRD]-ait:traceability -->
### 需求:可追溯——spec→代码(目标1)

**用户故事:** 作为维护者,我希望任一代码制品都能唯一追溯回它的 PRD,并让 codegen 沿这条链为 AI 组装上下文,以便定位待改代码并给 AI 完整依据。

#### 验收标准
1. WHEN 对任一叶 TDD 执行 codegen prepare THEN 输出含其唯一 target_file、上溯的 FSD/PRD 全链、以及路径上 depends_on 兄弟的能力契约。
2. WHEN 无活动版本 THEN codegen 从 baseline 解析,行为一致。
3. 每个制品文件沿 `TDD → FSD → PRD` 的关系链可唯一追溯到 PRD(六不变式第 6 条,门禁强制)。

<!-- @id:[PRD]-ait:parallel_isolation -->
### 需求:可拆分——并行不冲突(目标2)

**用户故事:** 作为维护者,我希望把系统递归分解成互不重叠的功能子树、不同人领不同子树,并保证不同 TDD 不会落到同一文件,以便多人/多 agent 并行开发时零文件冲突。

#### 验收标准
1. WHEN 两个 TDD 声明同一 target_file(归一化后)THEN 系统 SHALL 报 DUPLICATE_TARGET_FILE 拒于落盘之前。
2. WHEN 校验版本图 THEN 结构合法性(decomposes/details/depends_on 的类型与根-split 规则、FSD 不混子)通过。
3. 每个制品文件恰由 1 个 TDD 持有(六不变式第 3 条,门禁强制)。

<!-- @id:[PRD]-ait:invariant_governance -->
### 需求:六不变式的代码级强制

**用户故事:** 作为 AI 协作开发者,我希望规格树的完整性由 AIT 自身能力强制而非靠人自觉,以便任何违反结构约束的改动都无法被合入,规格始终自洽。

#### 验收标准
1. WHEN version confirm/merge THEN 系统 SHALL 对 baseline∪版本的组合视图全量校验六不变式:①每份 PRD 恰与 1 个 FSD 关联 ②每个 TDD 向上恰 1 个 FSD、向下恰 1 个制品 ③每个制品恰由 1 个 TDD 持有 ④所有关联经真实存在的 chunk ⑤除树根外无孤儿 chunk ⑥任一制品沿 TDD→FSD→PRD 可追溯。
2. IF 任一不变式被违反 THEN merge 报 INVARIANT_VIOLATION 拒于任何落盘之前(可重复跑、零落盘、修复后重试)。
3. WHEN 写入时试图建立永远非法的关联(幽灵端点、TDD 第二父、PRD 第二 FSD、制品撞车)THEN 写时局部门禁拒之,零落盘。
4. WHEN 配置了制品验收命令 THEN confirm/merge 前置运行之,exit≠0 报 ACCEPTANCE_FAILED 拒于落盘之前。
