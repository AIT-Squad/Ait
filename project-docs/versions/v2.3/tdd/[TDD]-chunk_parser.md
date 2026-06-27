<!-- @id:[TDD]-chunk_parser -->
## chunk_parser TDD

<!-- @summary: parse_file/parse_text：@id/@ref/@extract 解析、代码围栏屏蔽、[PRD]/[FSD]/[TDD] br target_file skill/ait/ait/chunk_parser.py。 -->

```yaml
target_file: skill/ait/ait/chunk_parser.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

parse_file/parse_text：@id/@ref/@extract 解析、代码围栏屏蔽、[PRD]/[FSD]/[TDD] bracket 前缀、内部 split `:`、summary 提取。

### 单元测试要求

测试位于 tests/test_chunk_parser.py：覆盖正常路径、边界与错误路径。
