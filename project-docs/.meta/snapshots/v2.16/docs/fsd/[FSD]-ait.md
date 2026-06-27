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
`ait version` commit/confirm/merge/reset/status：三态提交、原子 confirm（两阶段+回退）、chunk 级合并。

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
