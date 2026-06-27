<!-- @id:[TDD]-impact -->
## impact TDD

<!-- @summary: 影响查询：返回改动某 chunk 的下游影响面。 target_file skill/ait/ait/impact.py。 -->

```yaml
target_file: skill/ait/ait/impact.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

影响查询：返回改动某 chunk 的下游影响面。

### 单元测试要求

测试位于 tests/（specgraph 相关）：覆盖正常路径、边界与错误路径。
