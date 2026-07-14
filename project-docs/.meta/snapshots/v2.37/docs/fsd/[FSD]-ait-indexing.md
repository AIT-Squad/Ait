<!-- @id:[FSD]-ait-indexing -->
## indexing FSD

### 功能范围

索引重建与历史迁移：baseline/version chunks-index 的扫描重建、加载、查询；一次性 schema 迁移（block→chunk）。chunks-index 管「块自身状态」（与 specgraph 管关系互补）。

### 交互契约

- 重建：`rebuild_baseline()->（BaselineIndex,LinksIndex)`、`scan_dir/build_baseline/build_links`。
- 查询：`query_baseline(chunk_id)`、`query_version(version,chunk_id)`、`load_baseline/load_version_index/save_version_index/all_version_records/list_versions`。
- 迁移：`migrate_block_to_chunk(meta_dir, dry_run)`。

<!-- @id:[FSD]-ait-indexing:index_manager -->
## index_manager
### 功能描述
IndexManager：路径助手；scan_dir 解析 docs/version markdown；build_baseline（从 docs/ 重建 BaselineIndex，含 global category）、build_links、rebuild_baseline；query_baseline/query_version；load/save_version_index；_compute_stats/_compute_tasks_summary（三态/action/task 计数）；list_versions。详见 [TDD]-index_manager。

<!-- @id:[FSD]-ait-indexing:migrations -->
## migrations
### 功能描述
migrate_block_to_chunk：把历史 block 术语/字段一次性迁移为 chunk（重命名 keys + index 文件），dry_run 预览，含校验与原子写。详见 [TDD]-migrations。
