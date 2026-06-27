<!-- @id:[TDD]-schemas -->
## schemas TDD

```yaml
target_file: skill/ait/ait/schemas.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

pydantic 数据模型：VersionMeta/VersionIndex/VersionChunkEntry/ChangeRecord/CommitEntry/State 等 + 错误码集合。

### 单元测试要求

测试位于 tests/（schema 相关）：覆盖正常路径、边界与错误路径。
