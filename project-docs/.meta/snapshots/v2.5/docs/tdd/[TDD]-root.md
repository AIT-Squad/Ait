<!-- @id:[TDD]-root -->
## root TDD

```yaml
target_file: skill/ait/ait/root.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

项目根解析：定位含 project-docs 的根、CWD 校验（NOT_AT_PROJECT_ROOT / CWD_INSIDE_PROJECT_DOCS）。

### 单元测试要求

测试位于 tests/test_root_resolution.py：覆盖正常路径、边界与错误路径。
