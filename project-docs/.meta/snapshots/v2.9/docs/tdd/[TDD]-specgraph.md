<!-- @id:[TDD]-specgraph -->
## specgraph TDD

```yaml
target_file: skill/ait/ait/specgraph.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

SpecGraph：spec/edge 模型、load/save、dry_run_merge、combined_specgraph、resolve_chunk_uri、@ref 建边、export_dot；baseline + per-version 分文件。

### 单元测试要求

测试位于 tests/test_specgraph*.py：覆盖正常路径、边界与错误路径。
