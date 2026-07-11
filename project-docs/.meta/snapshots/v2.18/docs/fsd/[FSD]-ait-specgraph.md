<!-- @id:[FSD]-ait-specgraph -->
## specgraph FSD

### 功能范围

spec 关系图（块间关系视角，替代 links-index）：spec/edge 模型、URI 体系、从 @ref 重建 + 保留显式边、依赖/影响/成环查询、dot 导出、baseline+per-version 分文件与合并。提供 deps/impact 查询命令。

### 交互契约

- 图：`load_specgraph/combined_specgraph(baseline+version)/sync_specgraph/resolve_chunk_uri`。
- 查询：`SpecGraph.query/dependencies/implementations/impacted/detect_cycle/implements_of`。
- 合并：`dry_run_merge/merge_into_baseline`；`add_edge`。
- 命令：`query_deps`(deps)、`analyze_impact`(impact)。

<!-- @id:[FSD]-ait-specgraph:specgraph -->
## specgraph
### 功能描述
SpecGraph(specs/edges) + URI 体系(spec:{type}:{version}:{chunk})。sync_specgraph 从所有 docs/version markdown 的 @ref 重建图，并 _preserve_explicit_edges 保留 fsd link 加的显式边（故 reindex 不丢 decomposes/details/depends_on）。详见 [TDD]-specgraph。

<!-- @id:[FSD]-ait-specgraph:deps -->
## deps
### 功能描述
`query_deps(target,direction)`：解析 target→URI，返回该 chunk 的 in/out/both 关系边。详见 [TDD]-deps。

<!-- @id:[FSD]-ait-specgraph:impact -->
## impact
### 功能描述
`analyze_impact(target)`：返回改动 target 的下游影响 chunk 列表与计数。详见 [TDD]-impact。
