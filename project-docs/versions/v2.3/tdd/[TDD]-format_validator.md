<!-- @id:[TDD]-format_validator -->
## format_validator TDD

<!-- @summary: PRD/impl 格式校验：四段结构、summary 必需、派生命名 DERIVED_NAME、@extract 边界。 target_file skill/ait/ait/format_validator.py。 -->

```yaml
target_file: skill/ait/ait/format_validator.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

PRD/impl 格式校验：四段结构、summary 必需、派生命名 DERIVED_NAME、@extract 边界。

### 单元测试要求

测试位于 tests/（format 相关）：覆盖正常路径、边界与错误路径。
