<!-- @id:[TDD]-merge_engine -->
## merge_engine TDD

```yaml
target_file: skill/ait/ait/merge_engine.py
```

### 技术栈

Python 3.10+ / pydantic / PyYAML / click（按需）。

### 文件职责

merge_file/merge_new_file：把版本 chunk 合并进 baseline，**按 baseline 真实存在性逐 chunk 判定 action，绝不静默丢 chunk**。内置规则：

- **modify = 整块全替换**：version 侧提供该 chunk 的完整最终内容（要保留的内容须自带），整个替换 baseline 对应 chunk。
- **add = 仅用于 baseline 不存在的新 chunk**。
- **按存在性自动判定**：`modify` 的目标（`overrides` 缺省取 chunk 自身 id）若**不在 baseline，则当作 add 追加**（保留位置顺序），不再静默跳过丢弃；在 baseline 则全替换。
- `add` 命中 baseline 已存在的 chunk 仍报错（提示改用 modify）。
- `delete` 删除 `overrides` 指向的 baseline chunk。
- 保留文件容器（file_header）。

### 单元测试要求

测试位于 tests/test_merge_engine.py：覆盖 modify 全替换、add 新增、delete、`add` 命中已存在报错，以及**回归用例：一个文件含「已存在根(modify) + 新 split(modify 但不在 baseline)」时，所有 split 必须落入 baseline markdown，不被丢弃**。
