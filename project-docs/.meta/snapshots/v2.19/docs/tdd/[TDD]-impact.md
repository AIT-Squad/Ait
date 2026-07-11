<!-- @id:[TDD]-impact -->
## impact TDD

```yaml
target_file: skill/ait/ait/impact.py
```

### 技术栈
Python 3.10+；依赖 `specgraph.combined_view`、`version_manager.VersionManager`。

### 代码结构
`analyze_impact(project_root, target) -> dict`：version=current()；view=combined_view(root,version)；target 直接以 chunk_id 解析（view.node 不存在→`{"target":target,"impacted":[],"count":0,"found":false}`）；impacted=view.impacted(target)——**正向 decomposes/details 边＋id 结构子（冒号 split 隶属其根）＋反向 depends_on/implements（依赖方）** 的传递闭包——规格树下游全覆盖：改 PRD 波及 FSD 全树与 TDD；返回 `{target:chunk_id, impacted:list[chunk_id], count:len, found:true}`。被 modify 进版本的 chunk 与 baseline chunk 同身份（组合视图消除 URI 二象性）。

### 边界条件
target 不存在于视图→found:false 空集不报错；环上节点不重复出现、不含起点。

### 单元测试要求
`tests/`（specgraph/impact 相关）：改 PRD → impacted 含 decomposes 子 FSD、根的冒号 split（无边的结构子）与 details 孙 TDD；反向 depends_on 依赖方纳入；target 为版本中 modify 的 chunk 时结果与 baseline 身份一致；不存在的 target → found:false。pytest。
