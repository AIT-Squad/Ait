<!-- @id:[TDD]-migrations -->
## migrations TDD

```yaml
target_file: skill/ait/ait/migrations.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

一次性数据迁移：block→chunk 等历史 schema 迁移（migrate-block-to-chunk）。

### 单元测试要求

测试位于 tests/（migration 相关）：覆盖正常路径、边界与错误路径。
