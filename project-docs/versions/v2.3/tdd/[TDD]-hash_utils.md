<!-- @id:[TDD]-hash_utils -->
## hash_utils TDD

<!-- @summary: chunk_hash：chunk 内容哈希（用于 base_hash 失效检测）。 target_file skill/ait/ait/hash_utils.py。 -->

```yaml
target_file: skill/ait/ait/hash_utils.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

chunk_hash：chunk 内容哈希（用于 base_hash 失效检测）。

### 单元测试要求

测试位于 tests/（hash 相关）：覆盖正常路径、边界与错误路径。
