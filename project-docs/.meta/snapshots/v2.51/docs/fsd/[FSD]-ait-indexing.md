<!-- @id:[FSD]-ait-indexing -->
## indexing 内部分解

### 功能描述
indexing 域的实现分解。该域负责索引的重建、加载、查询与一次性历史迁移。chunks-index 记录"块自身状态"(每个 chunk 的 action/state/统计),与 specgraph 记录"块间关系"互补,二者分工不重叠。它从 doc_model 的解析器拿到 chunk 结构,把它们组织成 baseline 索引(全库当前态)与 version 索引(单版本工作态)。实现拆为两个文件:index_manager(索引重建与查询)与 migrations(block→chunk 历史术语迁移)。

### 反向要求
- 不管理块间关系(decomposes/details/depends_on 归 specgraph 域,本域只管块自身状态)。
- 不解析 markdown 语法(委托 doc_model 的 chunk_parser)、不做原子写(委托 foundation 的 io_utils)。
- 本文件不定义域对外公共接口(域契约在顶层文件 [FSD]-ait 的 indexing 域块,本文件是内部实现分解)。

### 分解视图
- index_manager 叶(details → [TDD]-index_manager):索引重建、加载、查询
- migrations 叶(details → [TDD]-migrations):block→chunk 一次性历史迁移

<!-- @id:[FSD]-ait-indexing:index_manager -->
## index_manager
### 功能描述
IndexManager 类,索引的重建者与查询者。职责:路径助手(baseline/version 索引文件与目录定位、按 file 名查找 baseline 或 version 内的文档);scan_dir 调 doc_model 解析器把一个目录下的 markdown 全部解析成 ParsedFile 列表;build_baseline 从 docs/ 重建 BaselineIndex(含 global 分类)、build_links 重建 LinksIndex、rebuild_baseline 一次产出二者;query_baseline 按 chunk_id 查基线条目、query_version 查某版本条目、all_version_records 取某 chunk 在版本内的全部历史记录;load/save_version_index 读写版本索引;内部 _compute_stats 与 _compute_tasks_summary 汇总三态/action/task 计数;list_versions 列出全部版本名。

### 反向要求
- 不建立或读取关系图(关系归 specgraph 域,本类只读 chunk 自身状态)。
- 不解析 markdown(把文本转 chunk 委托 doc_model 的 chunk_parser,本类只组织解析结果)。
- 不做版本生命周期编排(三态流转与合并归 version 域,本类只提供索引读写原语)。

<!-- @id:[FSD]-ait-indexing:migrations -->
## migrations
### 功能描述
一次性历史 schema 迁移。migrate_block_to_chunk 把历史遗留的 block 术语与字段名整体重命名为 chunk(递归重命名 YAML 键 + 重命名 index 文件),返回 MigrationReport 汇总改动;支持 dry_run 预览(只报告不落盘);迁移前 _validate_or_raise 校验前置条件,写入走原子写。这是历史遗留数据的一次性升级工具,不是常态流程的一环。

### 反向要求
- 不做常态索引重建(那是 index_manager 的职责,本文件仅处理历史术语升级)。
- 不触碰块间关系与业务语义(只做机械的键/文件重命名)。
- 不在非 dry_run 下做无校验的破坏性改动(改动前必先校验)。

<!-- @id:[FSD]-ait-indexing:TEST -->
## TEST 集成验收
indexing 域所有部件(index_manager + migrations)合并到一起、作为整体的集成验收:
1. WHEN 对含多个 chunk 文档的 docs/ 调 rebuild_baseline THEN 得到 BaselineIndex 与 LinksIndex,每个 chunk 按其 @id 与所在文件正确入索引,统计计数与实际 chunk 一致。
2. WHEN 用 chunk_id 调 query_baseline / 用 (version,chunk_id) 调 query_version THEN 命中返回对应条目、未命中返回 None;all_version_records 返回该 chunk 在版本内的全部历史记录。
3. WHEN save_version_index 写版本索引再 load_version_index 读回 THEN 得到等价索引(round-trip),三态/action/task 统计字段正确重算。
4. WHEN 对含 block 术语的历史 .meta 调 migrate_block_to_chunk(dry_run=True) THEN 只返回预览报告不落盘;dry_run=False 则原子重命名键与文件并返回 MigrationReport。
5. IF 迁移前置校验不通过 THEN 抛 MigrationError 且不做任何破坏性改动。
