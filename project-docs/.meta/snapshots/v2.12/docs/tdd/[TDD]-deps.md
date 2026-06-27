<!-- @id:[TDD]-deps -->
## deps TDD

```yaml
target_file: skill/ait/ait/deps.py
```

### 技术栈
Python 3.10+；依赖 `specgraph.combined_specgraph/resolve_chunk_uri`、`version_manager.VersionManager`。

### 代码结构
`query_deps(project_root, target, *, direction="both") -> dict`：version=VersionManager.current()；graph=combined_specgraph(root,version)；uri=resolve_chunk_uri(target)；edges=graph.query(uri,direction)；返回 `{target:uri, direction, edges:[edge.__dict__ …]}`。

### 单元测试要求
`tests/`（specgraph/deps 相关）：out/in/both 方向返回正确边。pytest。
