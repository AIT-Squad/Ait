<!-- @id:[FSD]-ait -->
## ait 功能分解根

### 功能范围

AIT 的功能按 CLI 命令域分解为子 FSD。命令域：init/prd/impl/task/version/new-model/specgraph/context/state/lint/search/indexing；外加分发器 cli、skill 层域与两个基础设施域 doc-model、foundation。每个域 decomposes 一个子 FSD，子 FSD details 到 TDD，每个 TDD 唯一映射一个 .py 文件。

### 功能依赖（域间，详见 specgraph depends_on）

按真实 import 导出的域间依赖（同父 split 层的 depends_on 边，约 69 条）：cli 依赖全部命令域；prd→（doc_model/indexing/version/lint/foundation）；impl→prd 等；version/new_model/specgraph/init/context/state/search/indexing 依赖 doc_model/foundation 等基础设施。foundation 与 doc_model 是叶依赖（被依赖、不依赖业务域）。

<!-- @id:[FSD]-ait:init -->
## init 域
### 功能描述
`ait init`：旧模型 global 基线 + 新模型 prd/fsd/tdd 骨架（--new-model），生成项目 wrapper。

<!-- @id:[FSD]-ait:prd -->
## prd 域
### 功能描述
`ait prdv1` create/save-draft/confirm/commit/show：旧模型 PRD 四段结构、req 草稿、确认锁定。

<!-- @id:[FSD]-ait:impl -->
## impl 域
### 功能描述
`ait impl` create/commit/lock/inherit：1 PRD→N impl、@extract、@ref implements、pre-merge 校验。

<!-- @id:[FSD]-ait:task -->
## task 域
### 功能描述
`ait task` create/execute/complete/fail/list/show：从 specgraph 派生 task、聚焦上下文、回写 code_refs。

<!-- @id:[FSD]-ait:version -->
## version 域
### 功能描述
版本生命周期与基线合并。一个"版本"是一次变更的原子单元(全有或全无):chunk 在版本工作区经历三态(working 可反复修改 → staged 中间态 → committed 锁定不可改),锁定后经纯门禁校验,一次性原子合入基线并产生一个 git 提交;任一步失败则把 docs 与 .meta 关键状态按字节还原(不残留半合入状态),可修复后重试;不满意可整版物理清空退出。confirm 门禁是六不变式的全局权威闸口——六不变式即规格治理的六条硬约束:①每份 PRD 恰与 1 个 FSD 关联;②每个 TDD 向上恰有 1 个 FSD(details 入边)、向下恰有 1 个制品文件;③每个制品路径只由 1 个 TDD 持有;④所有关联经真实存在的 chunk(无幽灵边);⑤除规格树根外无孤儿 chunk;⑥任一制品沿 TDD→FSD→PRD 可追溯。任何一条违例,合入即被拒于任何落盘之前。配置制品验收命令后,门禁还会先跑测试,红则同样拒绝。

### 反向要求
- 不解析单个 chunk 的语法与边界(归 doc_model 域)。
- 不存储、不查询 chunk 间关系图(归 specgraph 域)。
- 不生成任何业务代码或制品内容(归 new_model 域的 codegen)。
- 不做多用户并发锁(单用户本地工具边界)。

### 能力契约
- **提供方式**:Python 类 `VersionManager(project_root)`
- **接口**:
  - 生命周期:`create(version, based_on=None) -> VersionMeta`(已存报错)、`current() -> str|None`、`list_versions() -> list[VersionMeta]`
  - 三态:`stage(version, chunk_ids=None) -> StageResult{staged,skipped}`、`commit(version, message) -> CommitResult{commit_id,changes}`、`uncommit(version, chunk_ids) -> {reverted,not_found}`、`status(version) -> StatusReport{version,working,staged,committed,by_action}`
  - 纯门禁:`gate(version) -> {passed, violations:[{code,message,chunk_id}], acceptance}`(零落盘可重复)
  - 原子合入:`confirm(version, *, allow_dirty_git=False, conflict_policy="use-version") -> {merged_chunks, commit, git}`(失败字节级回退)
  - 逃生:`reset(version, *, confirmed) -> dict`
  - 验收:`run_acceptance() -> {passed,skipped,command,exit_code}` / `set_acceptance_command(cmd)`
  - 错误:`VersionManagerError{code}` ∈ {CHUNK_LOCKED,COMMIT_EMPTY,GIT_DIRTY,MERGE_NO_COMMITTED,MERGE_ROLLBACK,GIT_COMMIT_FAILED,INVARIANT_VIOLATION,ACCEPTANCE_FAILED,MODIFY_RENAME_COLLISION,DUPLICATE_OVERRIDES_TARGET,DUPLICATE_BASELINE_CHUNK,TASK_NOT_DONE}

<!-- @id:[FSD]-ait:new_model -->
## new-model 域
### 功能描述
`ait prd/fsd/tdd/codegen`：新模型文档创建、显式建边、图校验、target_file 唯一性、codegen 上下文组装。

<!-- @id:[FSD]-ait:specgraph -->
## specgraph 域
### 功能描述
`ait specgraph/deps/impact`：spec 关系图、edge 管理、依赖与影响查询、dot 导出、新模型图校验。

<!-- @id:[FSD]-ait:context -->
## context 域
### 功能描述
`ait context`：L1+L2 上下文装配（prd-to-impl / impl-edit 场景）。

<!-- @id:[FSD]-ait:state -->
## state 域
### 功能描述
`ait state`：渲染版本进度面板（三态分布、impl 覆盖、task 状态），可保存 state.md。

<!-- @id:[FSD]-ait:lint -->
## lint 域
### 功能描述
`ait lint`：旧模型 PRD/impl 格式与结构校验（与新模型图校验分离）。

<!-- @id:[FSD]-ait:search -->
## search 域
### 功能描述
`ait search`：跨 chunk 全文检索。

<!-- @id:[FSD]-ait:indexing -->
## indexing 域
### 功能描述
`ait reindex/baseline-summary/migrate-block-to-chunk`：从文件重建 chunks-index、baseline 摘要、一次性数据迁移。

<!-- @id:[FSD]-ait:cli -->
## cli 分发器
### 功能描述
`ait` 入口：click 命令路由、统一 JSON 输出契约、项目根解析；只分发不含业务逻辑。

<!-- @id:[FSD]-ait:doc_model -->
## doc-model 基础设施
### 功能描述
chunk_parser（@id/@ref/@extract 解析）+ schemas（pydantic 数据模型）；被所有域依赖。

<!-- @id:[FSD]-ait:foundation -->
## foundation 基础设施
### 功能描述
root（项目根解析）+ io_utils（原子写）+ yaml_io（模型存取）+ hash_utils（chunk 哈希）。

<!-- @id:[FSD]-ait:skill -->
## skill 层
### 功能描述
SKILL.md 主清单（路由/全局契约/命令速查/Pipeline）+ 6 个 sub-skills；不是 .py 代码，是 skill 基础设施（生成目标，可作 target_file）。
