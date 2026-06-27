<!-- @id:[TDD]-yaml_io -->
## yaml_io TDD

<!-- @summary: save_model/load_model：pydantic 模型 ↔ YAML 文件存取。 target_file skill/ait/ait/yaml_io.py。 -->

```yaml
target_file: skill/ait/ait/yaml_io.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

save_model/load_model：pydantic 模型 ↔ YAML 文件存取。

### 单元测试要求

测试位于 tests/（yaml 相关）：覆盖正常路径、边界与错误路径。
