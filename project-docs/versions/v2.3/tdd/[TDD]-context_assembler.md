<!-- @id:[TDD]-context_assembler -->
## context_assembler TDD

<!-- @summary: ContextAssembler：assemble(L1 目标 chunk + L2 SpecGraph 依赖)，prd-to-impl / target_file skill/ait/ait/context_assembler.py。 -->

```yaml
target_file: skill/ait/ait/context_assembler.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

ContextAssembler：assemble(L1 目标 chunk + L2 SpecGraph 依赖)，prd-to-impl / impl-edit 场景，focus/deps 选项。

### 单元测试要求

测试位于 tests/test_prd_impl_context.py：覆盖正常路径、边界与错误路径。
