<!-- @id:[TDD]-impact -->
## impact TDD

```yaml
target_file: skill/ait/ait/impact.py
```

### 技术栈
Python 3.10+；依赖 `specgraph.combined_specgraph/resolve_chunk_uri`、`version_manager.VersionManager`。

### 代码结构
`analyze_impact(project_root, target) -> dict`：version=current()；graph=combined_specgraph；uri=resolve_chunk_uri(target)；impacted=graph.impacted(uri)（反向可达）；返回 `{target:uri, impacted:list, count:len}`。

### 单元测试要求
`tests/`（specgraph/impact 相关）：下游影响闭包正确。pytest。
