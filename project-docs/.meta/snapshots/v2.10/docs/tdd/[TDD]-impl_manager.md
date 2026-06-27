<!-- @id:[TDD]-impl_manager -->
## impl_manager TDD

```yaml
target_file: skill/ait/ait/impl_manager.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

ImplManager：create（自动注入 @ref implements）、commit（pre-merge：成环/重复 @id/@extract 目标）、inherit、lock；@extract 标记动态 global 片段。

### 单元测试要求

测试位于 tests/test_impl_*.py：覆盖正常路径、边界与错误路径。
