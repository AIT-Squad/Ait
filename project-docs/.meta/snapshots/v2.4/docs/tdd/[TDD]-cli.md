<!-- @id:[TDD]-cli -->
## cli TDD

```yaml
target_file: skill/ait/ait/cli.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

click 命令树：init/prd/impl/task/version/fsd/tdd/codegen/prdv2/specgraph/context/state/lint/search/deps/impact/reindex 等；ok/fail 统一 JSON 契约；_root 项目根解析；只分发。

### 单元测试要求

测试位于 tests/test_new_model_commands.py 等 CLI 测试：覆盖正常路径、边界与错误路径。
