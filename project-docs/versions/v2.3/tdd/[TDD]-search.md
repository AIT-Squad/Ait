<!-- @id:[TDD]-search -->
## search TDD

<!-- @summary: search：跨 baseline/version chunk 的全文关键词检索，返回命中 chunk 与位置。 target_file skill/ait/ait/search.py。 -->

```yaml
target_file: skill/ait/ait/search.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

search：跨 baseline/version chunk 的全文关键词检索，返回命中 chunk 与位置。

### 单元测试要求

测试位于 tests/（search 相关）：覆盖正常路径、边界与错误路径。
