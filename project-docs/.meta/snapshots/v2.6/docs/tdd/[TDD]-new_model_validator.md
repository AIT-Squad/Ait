<!-- @id:[TDD]-new_model_validator -->
## new_model_validator TDD

```yaml
target_file: skill/ait/ait/new_model_validator.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

validate_prd_fsd_tdd_graph：关系合法性（decomposes PRD/FSD→FSD、details 叶FSD→TDD、depends_on 同父兄弟）、FSD 不混 FSD/TDD 子；validate_target_file_uniqueness：DUPLICATE_TARGET_FILE。

### 单元测试要求

测试位于 tests/test_new_model_validator.py：覆盖正常路径、边界与错误路径。
