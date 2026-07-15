<!-- @id:[FSD]-ait -->
## ait 功能分解根

### 功能描述
AIT 的功能按命令域分解为子 FSD。AIT 是 chunk 级规格版本控制与 AI 实现编排系统:把 PRD(需求意图)→FSD(功能分解)→TDD(文件级技术设计)→codegen(AI 编码)组织为可门禁、可回退、可追溯的管线。本根文件承接 [PRD]-ait 的全部需求,把系统分解为 16 个命令域:9 个现行域——foundation(基础设施)、doc_model(文档模型)、indexing(索引)、specgraph(关系图)、version(版本生命周期)、new_model(新模型引擎)、cli(命令分发)、init(初始化)、skill(分发资产);7 个 legacy 域——prd、impl、task、state、search、context、lint(旧模型流程,可用但不再演进)。每个域 decomposes 一个子 FSD 文件做内部分解,子 FSD 的叶 split details 到 TDD,每个 TDD 唯一映射一个制品文件。

### 反向要求
- 本文件不承载域间依赖关系:域 split 之间的 depends_on 边只存于 SpecGraph(经 ait deps/impact 查询),文档正文零关系声明。
- 本文件不描述各域内部实现(内部分解在各域子 FSD 文件,文件级设计在各 TDD)。
- 不为 legacy 域维护能力契约(legacy 域契约冻结于现状实现,随将来退役一并处理)。

### 分解视图
- foundation 域(decomposes → [FSD]-ait-foundation):项目根解析、原子写与路径守卫、YAML 存取、内容哈希
- doc_model 域(decomposes → [FSD]-ait-doc_model):chunk 解析器与全部持久化 schema
- indexing 域(decomposes → [FSD]-ait-indexing):chunks-index 重建/查询与历史迁移
- specgraph 域(decomposes → [FSD]-ait-specgraph):块间关系图、组合视图、deps/impact 查询
- version 域(decomposes → [FSD]-ait-version):版本生命周期、三态、门禁、原子合入
- new_model 域(decomposes → [FSD]-ait-new_model):新模型文档创建、关系出生、六不变式校验、codegen 上下文
- cli 域(decomposes → [FSD]-ait-cli):click 命令树与统一 JSON 输出契约
- init 域(decomposes → [FSD]-ait-init):项目初始化与骨架生成
- skill 域(decomposes → [FSD]-ait-skill):SKILL.md 清单、sub-skills、模板与参考资产
- legacy:prd/impl/task/state/search/context/lint 各 decomposes 对应子 FSD(旧模型流程)

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
## specgraph 关系图域

### 功能描述
块间关系(decomposes/details/depends_on/implements)的权威存储与查询:从 markdown 重建+保留命令建的显式边、组合视图(baseline∪版本坍缩到 chunk_id 世界)、依赖/影响/成环查询。是 codegen 上溯、六不变式校验、迭代定位的关系数据来源。内部分解见 [FSD]-ait-specgraph。

### 能力契约
- **提供方式**:Python 模块函数与类(ait.specgraph / ait.deps / ait.impact),CLI 命令 `ait deps` / `ait impact`
- **接口**:
  - `load_specgraph(root, version="baseline") -> SpecGraph`、`sync_specgraph(root)`——重建并保留显式边(source 标记的边跨 reindex 存活)
  - `combined_view(root, version=None) -> CombinedView`——chunk_id 世界:版本覆盖 baseline、边端点坍缩去重、depends_on 按 owned-scope 覆盖;`edges_from(id, rel=None)` / `edges_to(id, rel=None)` / `impacted(id)` / `detect_cycle()`
  - `add_edge(root, version, src, dst, rel, source)`——底层建边原语(仅供 new_model 域调用,无用户命令)
  - `query_deps(project_root, target, *, direction="both") -> {target, direction, edges}`——单跳邻接查询
  - `analyze_impact(project_root, target) -> {found, impacted, count}`——下游影响传递闭包(正向 decomposes/details + id 结构子 + 反向 depends_on/implements)

### 反向要求
- 不判定关系合法性(六不变式与基数约束归 new_model 校验器,本域忠实存取)。
- 不提供任何用户可用的 link/depend 建边命令(关系只随内容创建出生)。

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
## indexing 索引域

### 功能描述
chunks-index 的重建、加载、查询与一次性历史迁移。chunks-index 记录"块自身状态"(action/state/统计),与 specgraph 记录"块间关系"互补。内部分解见 [FSD]-ait-indexing。

### 能力契约
- **提供方式**:Python 类与函数(ait.index_manager.IndexManager / ait.migrations)
- **接口**:
  - `rebuild_baseline() -> (BaselineIndex, LinksIndex)`——从 docs/ 全量重建基线索引
  - `query_baseline(chunk_id) -> BaselineChunkEntry|None`、`query_version(version, chunk_id) -> VersionChunkEntry|None`、`all_version_records(version, chunk_id) -> list`
  - `load_baseline() / load_version_index(version) / save_version_index(index)`——索引读写(经 foundation 原子写)
  - `list_versions() -> list[str]`
  - `migrate_block_to_chunk(meta_dir, dry_run) -> MigrationReport`——block→chunk 术语一次性迁移,dry_run 预览
- 统计(三态/action/task 计数)在 save 时自动重算

### 反向要求
- 不管块间关系(归 specgraph 域)。
- 不解析 markdown(委托 doc_model)。

<!-- @id:[FSD]-ait:cli -->
## cli 分发器
### 功能描述
`ait` 入口：click 命令路由、统一 JSON 输出契约、项目根解析；只分发不含业务逻辑。

<!-- @id:[FSD]-ait:doc_model -->
## doc_model 文档模型域

### 功能描述
文档模型底座:把 markdown 解析成 chunk/ref/extract 结构(边界由 `<!-- @id -->` 注释决定),并定义全部 .meta 持久化数据的 pydantic schema。是"文档如何被解析"与"数据长什么样"的单一权威来源。内部分解见 [FSD]-ait-doc_model。

### 能力契约
- **提供方式**:Python 模块函数与 pydantic 模型(ait.chunk_parser / ait.schemas)
- **接口**:
  - `parse_file(path, base_dir) -> ParsedFile`、`parse_text(text, file) -> ParsedFile`——ParsedFile(file, file_header, chunks, refs);Chunk 带 id/heading/level/content/行号/no_impl/summary;Ref 带 source_chunk_id/target_file/target_chunk_id/rel
  - `parse_extract_blocks(text) -> list[ExtractBlock]`——@extract 成对解析,嵌套/未闭合抛 ExtractError
  - code-fence 内的 @id/@ref 被屏蔽;chunk id 支持 legacy 与 [PRD]/[FSD]/[TDD] 前缀(冒号 split 含保留大写 :TEST)
  - schema 类:ProjectConfig/BaselineIndex/VersionIndex/VersionChunkEntry/VersionMeta(含 phase 阶段机与锁定字段)/RequirementMeta/ChangeRecord/TaskYaml 等;类型别名 Action/State/VersionPhase/TaskStatus;StrictModel 基类 extra=forbid;summary ≤120 校验

### 反向要求
- 不建关系图、不校验六不变式(解析归此,语义校验归 new_model 域)。
- 不做文件 IO(读写与原子性归 foundation)。

<!-- @id:[FSD]-ait:foundation -->
## foundation 基础设施域

### 功能描述
通用基础设施底座:项目根解析、原子文件写与路径越界守卫、pydantic 模型与 YAML 互转、chunk 内容指纹。纯工具、无业务状态,被几乎所有域消费;自身不依赖任何业务域。内部分解见 [FSD]-ait-foundation。

### 能力契约
- **提供方式**:Python 模块函数与数据类(ait.root / ait.io_utils / ait.yaml_io / ait.hash_utils)
- **接口**:
  - `resolve_project_root() -> ProjectRoot(cwd, root, docs, meta)`——解析 `<CWD>/project-docs/` 为唯一合法工作根;错误:NOT_AT_PROJECT_ROOT / PROJECT_DOCS_MALFORMED / CWD_INSIDE_PROJECT_DOCS
  - `atomic_write_text(path, content, *, encoding="utf-8")` / `atomic_write_bytes(path, data)`——tmp+fsync+replace 原子写,不留半写文件
  - `ensure_within(project_root, target) -> Path`——路径越界守卫;越界抛 PathOutsideProjectError
  - `to_posix_rel(root, path) -> str`、`strip_md_ext(rel_path) -> str`
  - `load_yaml(path) -> dict`、`load_model(path, Model) -> Model`、`dump_model(model) -> str`、`save_model(path, model)`——YAML↔pydantic,稳定块状风格,datetime→isoformat
  - `normalize(text) -> str`(CRLF→LF+strip)、`chunk_hash(content) -> str`(SHA-256 前 8 hex)、`file_hash(content) -> str`

### 反向要求
- 不含业务语义(不知道 chunk/version/图为何物)。
- 不接受工作根覆盖配置(无 --root/环境变量,目录名硬编)。

<!-- @id:[FSD]-ait:skill -->
## skill 层
### 功能描述
SKILL.md 主清单（路由/全局契约/命令速查/Pipeline）+ 6 个 sub-skills；不是 .py 代码，是 skill 基础设施（生成目标，可作 target_file）。
