<!-- @id:[TDD]-merge_engine -->
## merge_engine TDD

<!-- @summary: merge_file/merge_new_file：按 action 把版本 chunk 合并进 baseline——modify 全替换  target_file skill/ait/ait/merge_engine.py。 -->

```yaml
target_file: skill/ait/ait/merge_engine.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

merge_file/merge_new_file：按 action 把版本 chunk 合并进 baseline——modify 全替换 overrides 目标、add 仅新增、delete 删除；保留文件容器。

### 单元测试要求

测试位于 tests/test_merge_engine.py：覆盖正常路径、边界与错误路径。
