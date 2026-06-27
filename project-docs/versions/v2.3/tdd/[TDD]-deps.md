<!-- @id:[TDD]-deps -->
## deps TDD

<!-- @summary: 依赖查询：返回某 chunk 的 depends_on / 上游关系。 target_file skill/ait/ait/deps.py。 -->

```yaml
target_file: skill/ait/ait/deps.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

依赖查询：返回某 chunk 的 depends_on / 上游关系。

### 单元测试要求

测试位于 tests/（specgraph 相关）：覆盖正常路径、边界与错误路径。
