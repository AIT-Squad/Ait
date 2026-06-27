<!-- @id:[TDD]-prd_manager -->
## prd_manager TDD

```yaml
target_file: skill/ait/ait/prd_manager.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

PrdManager：create/save_draft/confirm/commit/show；四段结构与 summary 必需校验；req 草稿持久化；commit 锁定写保护。

### 单元测试要求

测试位于 tests/test_prd_*.py：覆盖正常路径、边界与错误路径。
