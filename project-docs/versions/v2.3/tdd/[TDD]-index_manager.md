<!-- @id:[TDD]-index_manager -->
## index_manager TDD

<!-- @summary: IndexManager：baseline/version chunks-index 加载/保存/重建（rebuild_baseline）、 target_file skill/ait/ait/index_manager.py。 -->

```yaml
target_file: skill/ait/ait/index_manager.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

IndexManager：baseline/version chunks-index 加载/保存/重建（rebuild_baseline）、query_baseline/query_version、summary 索引。

### 单元测试要求

测试位于 tests/test_reindex.py：覆盖正常路径、边界与错误路径。
