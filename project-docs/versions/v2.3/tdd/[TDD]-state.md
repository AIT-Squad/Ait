<!-- @id:[TDD]-state -->
## state TDD

<!-- @summary: render_state/save_state：三态分布、impl 覆盖、task 状态、title/phase；markdown/json target_file skill/ait/ait/state.py。 -->

```yaml
target_file: skill/ait/ait/state.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

render_state/save_state：三态分布、impl 覆盖、task 状态、title/phase；markdown/json；可保存 versions/<v>/state.md。

### 单元测试要求

测试位于 tests/（state 相关）：覆盖正常路径、边界与错误路径。
