<!-- @id:[TDD]-index_manager -->
## index_manager TDD

```yaml
target_file: skill/ait/ait/index_manager.py
```

### 技术栈
Python 3.10+；依赖 `schemas`(BaselineIndex/BaselineChunkEntry/LinksIndex/VersionIndex/VersionChunkEntry/VersionIndexStats)、`chunk_parser`(parse_file/ParsedFile)、`yaml_io`(load_model/save_model)、`specgraph._global_category`(或等价)。

### 代码结构（IndexManager）
- `IndexSchemaViolation(Exception)`。
- 路径：`baseline_index_path/links_index_path/version_dir/version_index_path/find_baseline_file/find_version_file`。
- 扫描重建：`scan_dir(base_dir)->list[ParsedFile]`(遍历 *.md parse_file)；`build_baseline()->BaselineIndex`(扫 docs/，每 chunk→BaselineChunkEntry，含 file/heading/level/summary/metadata；global chunk 标 category)；`build_links()->LinksIndex`；`rebuild_baseline()->(BaselineIndex,LinksIndex)`(build + save 两者)。
- 加载查询：`load_baseline/load_links`；`query_baseline(chunk_id)->BaselineChunkEntry|None`；`load_version_index(version)/save_version_index(idx)`；`query_version(version,chunk_id)`；`all_version_records(...)`；`list_versions()`。
- 统计：`_compute_stats(idx)->VersionIndexStats`(total/by_action/by_state/tasks_summary)；`_compute_tasks_summary(version)`(读 tasks/*.yaml 计 status)。

### 关键约定
chunks-index 是「块状态台账」，与 specgraph「块关系」互补；baseline 从 docs/ markdown 重建（markdown 为真），version index 增量维护。

### 单元测试要求
`tests/test_reindex.py`：rebuild_baseline 从 markdown 重建、query_baseline/version、stats 计数。pytest。
