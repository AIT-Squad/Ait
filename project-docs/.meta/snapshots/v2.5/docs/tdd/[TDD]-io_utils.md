<!-- @id:[TDD]-io_utils -->
## io_utils TDD

```yaml
target_file: skill/ait/ait/io_utils.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

atomic_write_text：原子写文件（临时文件 + 替换）。

### 单元测试要求

测试位于 tests/（io 相关）：覆盖正常路径、边界与错误路径。
