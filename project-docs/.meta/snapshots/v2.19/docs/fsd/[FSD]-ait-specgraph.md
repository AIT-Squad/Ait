<!-- @id:[FSD]-ait-specgraph -->
## specgraph FSD

### 功能范围

spec 关系图（块间关系视角，替代 links-index）：spec/edge 模型、URI 体系、从 @ref 重建 + 保留显式边、依赖/影响/成环查询、dot 导出、baseline+per-version 分文件与合并；**组合图视图（chunk_id 世界）**——跨 baseline∪版本按 chunk 身份统一查询，供 codegen/deps/impact 消费。提供 deps/impact 查询命令。

### 交互契约

- 图：`load_specgraph/combined_specgraph(baseline+version)/sync_specgraph/resolve_chunk_uri`。
- 查询：`SpecGraph.query/dependencies/implementations/impacted/detect_cycle/implements_of`。
- **组合视图**：`combined_view(root,version)` → `CombinedView`——chunk 身份=chunk_id，版本覆盖 baseline（modify=同节点换内容来源），边端点坍缩为 chunk_id 并去重；`edges_from/edges_to/impacted/detect_cycle`。被 modify 进版本的 chunk 在视图中保有 baseline 期建立的全部关系（消除 URI 二象性）。
- 合并：`dry_run_merge/merge_into_baseline`；`add_edge`。
- 命令：`query_deps`(deps)、`analyze_impact`(impact)。

<!-- @id:[FSD]-ait-specgraph:specgraph -->
## specgraph
### 功能描述
SpecGraph(specs/edges) + URI 体系(spec:{type}:{version}:{chunk})。sync_specgraph 从所有 docs/version markdown 的 @ref 重建图，并 _preserve_explicit_edges 保留 fsd link 加的显式边（故 reindex 不丢 decomposes/details/depends_on）。CombinedView 在读取时把 baseline∪版本坍缩到 chunk_id 世界（存储格式不变，无数据迁移），成环检测在坍缩视图上进行（合并后才成环的图在合并前即可报出）。详见 [TDD]-specgraph。

<!-- @id:[FSD]-ait-specgraph:deps -->
## deps
### 功能描述
`query_deps(target,direction)`：在组合视图上解析 target→chunk_id，返回该 chunk 的 in/out/both 关系边（端点为 chunk_id）。被 modify 进版本的 chunk 查得到其全部既有关系。详见 [TDD]-deps。

<!-- @id:[FSD]-ait-specgraph:impact -->
## impact
### 功能描述
`analyze_impact(target)`：返回改动 target 的下游影响 chunk 列表与计数——正向 decomposes/details 边＋id 结构子（冒号 split 隶属其根）＋反向 depends_on/implements（依赖方）的传递闭包，供迭代流转"沿关联逐层向下改"定位。详见 [TDD]-impact。
