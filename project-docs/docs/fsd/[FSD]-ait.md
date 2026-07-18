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
## init 初始化域

### 功能描述
`ait init` 项目初始化:把目录引导为 AIT 可管理项目——生成 project-docs 骨架、项目 wrapper 与 config、按状态选全量/增量,支持新模型骨架(--new-model)。幂等。内部分解见 [FSD]-ait-init。

### 能力契约
- **提供方式**:Python 类(ait.init_manager.InitManager),CLI 命令 `ait init`
- **接口**:
  - `run(*, check_only=False, skip=(), new_model=False, project_name="project") -> InitResult(created_files, chunks, specs, skill_dir, cli_path, wrapper_path, status, files, skipped)`——fresh/incomplete/ready 状态判定;new_model=True 生成 docs/{prd,fsd,tdd} 与 [PRD]/[FSD] 根 + derives 派生边(直接入 specgraph,PRD 正文零关系);check_only 只报告
  - `refresh_wrapper() -> InitResult`——仅重写 wrapper
  - 错误:INVALID_PROJECT_NAME(名称非法/路径穿越)、BOOTSTRAP_FAILED(根 chunk 未入基线,防静默空基线)

- **白板起步 bootstrap(v2.54)**:init 在不含 project-docs 的空目录能自建骨架(docs/ 与 .meta/{versions,changes} 目录)后再引导——`ait init` 是白板入口,不因缺目录被根解析拒;其余命令仍要求项目根已存在。幂等(exist_ok),不破坏既有内容。
- **空基线保证(迭代连续性地基)**:init(含非 --new-model)确保 .meta 下空的基线索引与关系图文件落盘——初始=现状为空的迭代,任何背景检索逻辑零分支

- **空基线保证(迭代连续性地基)**:init(含非 --new-model)确保 .meta 下空的基线索引与关系图文件落盘——初始=现状为空的迭代,任何背景检索逻辑零分支
- **docs 仓独立化(v2.55)**:init 在 project-docs 内 `git init` 建独立 docs 仓(若不存在);在宿主根 .gitignore 追加 `project-docs/`(文本追加,零 git 操作守红线);在 docs 仓内写 .gitignore 排除 `versions/*/state.md`(派生产物不追踪)

### 反向要求
- 只搭骨架不创作内容(PRD/FSD/TDD 内容归各域 create 流)。
- 不覆盖已存在文件(幂等)。

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
## version 版本域

### 功能描述
版本生命周期与基线合并:版本是全有或全无的原子变更单元——chunk 三态流转(working→staged→committed)、锁定、纯门禁(可重复跑零落盘)、原子合入基线(失败字节级回退)、任意阶段整版退出、制品验收。confirm 是六不变式(①每份 PRD 恰与 1 个 FSD 关联 ②每个 TDD 向上恰 1 个 FSD、向下恰 1 个制品 ③每个制品恰由 1 个 TDD 持有 ④所有关联经真实存在的 chunk ⑤除树根外无孤儿 chunk ⑥任一制品沿 TDD→FSD→PRD 可追溯)的全局权威闸口。内部分解见 [FSD]-ait-version。

### 能力契约
- **提供方式**:Python 类(ait.version_manager.VersionManager),CLI 命令组 `ait version` / `ait acceptance`
- **接口**:
  - `version create <v>`——显式开版本(已存在报错);`current() -> str|None`、`list_versions()`
  - `version commit <v>`——全部 working chunk → committed 锁定(锁定后修改报 CHUNK_LOCKED);`uncommit(version, chunk_ids)` 层级返工原语(committed/staged→working,merged 拒)
  - `version confirm <v>`——纯门禁:`gate(version) -> {passed, violations, acceptance}`,汇集 task 完成度、重复/改名冲突(MODIFY_RENAME_COLLISION/DUPLICATE_OVERRIDES_TARGET)、六不变式、制品验收;可重复跑、零落盘
  - `version merge <v>`——原子合入:同一门禁前置→备份→逐文件合并 chunk→关系图提升入基线(depends_on 按 owned-scope 对账)→git 提交;任一步失败字节级回退报 MERGE_ROLLBACK;git 三分语义(非 git 环境 git:"unavailable"/无变更返回 HEAD/真实失败 GIT_COMMIT_FAILED 回滚)
  - `version revert <v> --confirm`——物理清空未合入版本
  - `acceptance set "<cmd>"` / `acceptance run`——配置/执行制品验收命令(exit≠0 → 门禁 ACCEPTANCE_FAILED;未配置跳过)
  - 错误:VersionManagerError{code} ∈ CHUNK_LOCKED/GIT_DIRTY/MERGE_ROLLBACK/GIT_COMMIT_FAILED/INVARIANT_VIOLATION/ACCEPTANCE_FAILED/VERSION_NOT_FOUND

- **GIT_DIRTY 预检已去除(v2.55)**:docs 仓在版本生命周期内故意 dirty(prd/fsd/tdd create 持续写入)是合法状态;confirm 不再因此失败;`--allow-dirty-git` 变无实质效果(保留接口兼容旧调用)
- **merge 记跨仓绑定字段(v2.55)**:merge 成功后写 `docs_commit`(docs 仓 commit sha)+`code_base`(只读宿主 HEAD,守红线);宿主非 git 仓时 code_base=None,merge 仍成功
- merge 原子性只覆盖 docs 仓;验收(`acceptance run`)仍在宿主根跑(制品在那里)

### 反向要求
- 不做 chunk 合并算法细节(域内 merge_engine 承担)、不算六不变式细节(调 new_model 校验器)。
- 不解析文档、不建关系边(分别归 doc_model/new_model 域)。

<!-- @id:[FSD]-ait:new_model -->
## new_model 新模型域

### 功能描述
新模型主线(PRD→FSD→TDD→codegen)的引擎:创建三类文档、关系随内容创建原子出生、六不变式校验内核、codegen 上下文组装。关系出生的四条路(四关系四出生地):derives 随 fsd create --parent(从 PRD 派生功能树根,创建即建边)、decomposes 随 fsd decompose(FSD 向下拆分即建边,仅限 FSD split→FSD 根)、details 随 tdd create --parent(叶子细化即建边)、depends_on 随 fsd create 的 split 内临时 yaml 声明(建边后从正文剥离,文档零关系声明);无任何 link/depend 命令,幽灵边从入口消灭。内部分解见 [FSD]-ait-new_model。

### 能力契约
- **提供方式**:Python 类与纯函数(ait.new_model_manager.NewModelManager / ait.new_model_validator),CLI 命令组 `ait prd` / `ait fsd` / `ait tdd` / `ait codegen`
- **接口**:
  - `prd create <id> --content*`——PRD 写入版本工作区;流转入口(无活动版本自动开版本,phase→prd-creating);`prd confirm` / `prd revert` 冻结-返工对
  - `fsd create <id> [--parent <prd-root>] --content*`——FSD 写入;--parent 给出时创建即建 derives 边(PRD 根→FSD 根,派生;父侧预检:parent 须为 PRD 根、已有 derives 出边报 PRD_FSD_LINK_NOT_UNIQUE);解析 split 内 depends_on 声明→建边→剥离;`fsd decompose <parent> <child> [--content]`——FSD 向下拆分即建 decomposes 边(仅限 FSD split 为 parent,PRD 不再经 decompose;父侧预检 MISSING_ENDPOINT);`fsd confirm` / `fsd revert`
  - `tdd create <id> --parent <fsd_split> --content*`——创建即建 details 边(预检 TDD_MULTI_PARENT);必含 target_file(缺失 TDD_TARGET_FILE_REQUIRED,归一化撞车 DUPLICATE_TARGET_FILE);`tdd confirm` / `tdd revert`
  - `codegen prepare <tdd_id> -> CodegenBundle`——组合视图上溯 TDD→FSD→PRD 全链 + 路径 depends_on 兄弟契约(被 modify 的 chunk 上下文完整)
  - `validate_invariants(view) -> list[NewModelViolation]`——六不变式全量校验(供 version 门禁消费);`check_edge_write` 写时局部门禁;`normalize_target_file`;违例码 PRD_FSD_LINK_NOT_UNIQUE/TDD_MULTI_PARENT/DUPLICATE_TARGET_FILE/MISSING_ENDPOINT/ORPHAN_CHUNK/TRACE_BROKEN/SPEC_CYCLE
    - **讨论背景模式(迭代连续性)**:prd/fsd/tdd create **省略 --content** 时不写盘,返回该层讨论背景 JSON(mode=discussion-context)——`prd create`→baseline 全部 PRD chunk 现状;`fsd create`→anchors(本版本 [PRD]- 改动 chunk 全文)+related(每锚点沿边一跳关联 chunk 全文)+target(目标 FSD 既有全文);`tdd create --parent <split>`→锚定式(parent 全文+邻接+上溯链+既有 details 子);`tdd create` 无 parent→发现式(本版本 [FSD]- 改动锚);`fsd decompose <parent> <child>` 无 content 且 child 不存在→锚定式(原为 MISSING_ENDPOINT 错误路径);全部经组合视图解析(版本改过取版本内容),过同层 phase 门禁,零写入
- fsd/tdd create 对不存在版本报 VERSION_NOT_FOUND(prd create 独享自动开版本)

### 反向要求
- 不存储关系(委托 specgraph)、不做版本门禁落盘(委托 version 域)。
- 不生成代码(codegen 只组装上下文,编码由 skill 层驱动 AI)。

<!-- @id:[FSD]-ait:specgraph -->
## specgraph 关系图域

### 功能描述
块间关系(derives/decomposes/details/depends_on/implements)的权威存储与查询:从 markdown 重建+保留命令建的显式边、组合视图(baseline∪版本坍缩到 chunk_id 世界)、依赖/影响/成环查询。是 codegen 上溯、六不变式校验、迭代定位的关系数据来源。内部分解见 [FSD]-ait-specgraph。

### 能力契约
- **提供方式**:Python 模块函数与类(ait.specgraph / ait.deps / ait.impact),CLI 命令 `ait deps` / `ait impact`
- **接口**:
  - `load_specgraph(root, version="baseline") -> SpecGraph`、`sync_specgraph(root)`——重建并保留显式边(source 标记的边跨 reindex 存活)
  - `combined_view(root, version=None) -> CombinedView`——chunk_id 世界:版本覆盖 baseline、边端点坍缩去重、depends_on 按 owned-scope 覆盖;`edges_from(id, rel=None)` / `edges_to(id, rel=None)` / `impacted(id)` / `detect_cycle()`
  - `add_edge(root, version, src, dst, rel, source)`——底层建边原语(仅供 new_model 域调用,无用户命令)
  - `query_deps(project_root, target, *, direction="both") -> {target, direction, edges}`——单跳邻接查询
  - `analyze_impact(project_root, target) -> {found, impacted, count}`——下游影响传递闭包(正向 derives/decomposes/details + id 结构子 + 反向 depends_on/implements)

  - `graph_md(root, version=None) -> str`——生成 Mermaid Markdown 字符串:节点=chunk id(特殊字符转义为合法 Mermaid node id,原 id 作 label);同文件 chunk 聚合进 `subgraph "<file>"` 框;边标注 derives/decomposes/details/depends_on;无数据时返回空图骨架。写文件到固定路径:baseline → `docs/graph.md`、version → `versions/<v>/graph.md`(原子写)。

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
## cli 命令分发域

### 功能描述
ait 命令行分发器:click 命令树把用户命令路由到各领域,统一 JSON 输出契约。只分发不含业务逻辑。内部分解见 [FSD]-ait-cli。

### 能力契约
- **提供方式**:CLI 入口(项目本地 wrapper `project-docs/.ait/ait-cli` → python -m ait.cli)
- **接口**:
  - 命令面:version(create/confirm/merge/revert/commit/status)、prd/fsd/tdd(create/confirm/revert + fsd decompose)、codegen(prepare)、deps/impact/specgraph、acceptance(set/run)、init、reindex;legacy(prdv1/impl/task/state/search/context/lint)
  - 输出契约:stdout 恒为单个 JSON——成功 `{"ok":true,"data":{...}}`,失败 `{"ok":false,"error":"...","code":"..."}`;click 用法错误也转 `{"ok":false,"code":"USAGE_ERROR"}`(不裸文本);--help 正常输出帮助
  - 领域错误码透传(issues[0].code),不吞成笼统码
  - 项目根解析:每次调用经 foundation 的 resolve_project_root,根错误以 JSON 报出

- **init 白板豁免(v2.54)**:main 命令组回调解析项目根失败为 NOT_AT_PROJECT_ROOT 时,若子命令是 init 则放行(root 指向待建的 <cwd>/project-docs,由 InitManager 建),其余命令仍按错误码拒——唯一 bootstrap 逃生口。

- **`ait specgraph graph-md [--version <v>]`(v2.56)**:无 --version 用 baseline,有则用 combined_view;写固定路径后输出路径+边数统计。

### 反向要求
- 不实现业务规则(只调 manager 转发结果与错误码)。
- 不维护任何跨调用状态。

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
## skill 分发资产域

### 功能描述
AIT 的 AI 使用面:SKILL.md 主清单(Claude 的 AIT 使用指令与命令速查)、6 个 sub-skills(状态面板/错误恢复/初始化引导等)、3 个文档模板(TEMPLATE-{PRD,FSD,TDD}-AIT-DRAFT.md,三类分化:PRD 问题空间/FSD 结构与契约/TDD 文件级实现)、7 个 references 参考资产(new-model-format 权威格式规范等)。全部为生成目标(target_file 指向分发文件)。内部分解见 [FSD]-ait-skill。

### 能力契约
- **提供方式**:随 skill 安装分发的 markdown 资产(~/.claude/skills/ait/)
- **接口**(文档契约):
  - SKILL.md——命令面权威速查、全局契约(入口 wrapper、JSON 输出、术语)、pitfalls
  - templates/TEMPLATE-{PRD,FSD,TDD}-AIT-DRAFT.md——三类文档的章节骨架(PRD:概述/范围/角色/目标/需求项+验收;FSD:功能描述/反向要求/分解视图/能力契约/:TEST;TDD:target_file/技术栈约束/文件职责/代码结构/实现逻辑/错误边界/单测)
  - references/new-model-format.md——格式权威规范(ID 语法/三关系/六不变式/生命周期/错误码全表)
- 更新纪律:代码行为变更须同步 SKILL.md 与相关 references(经 TDD spec 驱动)

### 反向要求
- 不含可执行代码(纯 markdown 资产;行为强制在代码侧门禁)。
- 模板不承载关系声明示例以外的关系语法(文档正文零关系原则)。

<!-- @id:[FSD]-ait:TEST -->
## TEST 系统级集成验收

ait 全部域(foundation/doc_model/indexing/specgraph/version/new_model/cli/init/skill + legacy)合并到一起、作为完整系统的端到端集成验收:

1. WHEN 在空项目 `ait init --new-model --name demo` → `prd create`(讨论出带 chunk 的 PRD)→ `prd confirm` → `fsd create`+`fsd decompose`(逐层分解,split 内声明依赖)→ `fsd confirm` → `tdd create --parent`(叶子细化,绑 target_file)→ `tdd confirm` → `codegen prepare` THEN 每步 stdout 为单个 JSON;关系边(decomposes/details/depends_on)随内容创建原子出生并只存于 SpecGraph(文档正文零关系声明);codegen 返回 TDD+上溯全链+依赖契约的完整上下文包。
2. WHEN 上述版本 `version commit` → `version confirm` THEN 门禁汇报六不变式(①PRD↔1FSD ②TDD↑1FSD↓1制品 ③制品↔1TDD ④关联经真实 chunk ⑤无孤儿 ⑥制品可追溯到 PRD)零违例与制品验收结果,可重复跑零落盘;`version merge` THEN 原子合入基线+一次 git 提交,任一步失败字节级回退不残留半合入状态。
3. WHEN 迭代:新版本 modify 任一 chunk(prd/fsd/tdd)THEN 组合视图下该 chunk 保有全部既有关系(deps/impact 可沿关系逐层定位波及面);改/删 split 依赖声明经 owned-scope 对账落到基线;chunk_id 不变则全部边跨版本存活。
4. IF 任何写入违反写时门禁(幽灵端点/TDD 第二父/PRD 第二 FSD/制品撞车/幽灵版本)THEN 拒于落盘前且零残留,修正后可重试;IF 版本违反六不变式 THEN merge 报 INVARIANT_VIOLATION 拒于任何落盘之前。
5. WHEN 每层 confirm 后 revert THEN 冻结解除、phase 回退、内容可继续修改(门禁配返工,无终态陷阱);`version revert` 整版退出不留残迹。
6. 全量测试套件(acceptance_command 配置的 pytest)通过是任何 merge 的前置条件——系统自身的演进也必须过自己的门禁(dogfood)。
