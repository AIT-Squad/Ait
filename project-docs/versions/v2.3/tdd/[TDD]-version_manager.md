<!-- @id:[TDD]-version_manager -->
## version_manager TDD

<!-- @summary: VersionManager：create/ensure/stage/commit/lock/confirm/reset；三态流转；conf target_file skill/ait/ait/version_manager.py。 -->

```yaml
target_file: skill/ait/ait/version_manager.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

VersionManager：create/ensure/stage/commit/lock/confirm/reset；三态流转；confirm 两阶段（precheck→merge→extract→specgraph 提升→git commit）失败回退。

### 单元测试要求

测试位于 tests/test_version_*.py、tests/test_merge_workflow.py：覆盖正常路径、边界与错误路径。
