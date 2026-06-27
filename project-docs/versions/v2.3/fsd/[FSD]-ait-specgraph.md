<!-- @id:[FSD]-ait-specgraph -->
## specgraph FSD

<!-- @summary: 关系图与依赖/影响查询域。details 到对应 TDD（一文件一映射）。 -->

### 功能范围

ait specgraph/deps/impact：关系图、建边、依赖与影响、dot 导出、新模型图校验。

<!-- @id:[FSD]-ait-specgraph:specgraph -->
## specgraph

<!-- @summary: SpecGraph：spec/edge 模型、load/save、dry_run_merge、combined_specgraph、resolve_chunk_ details [TDD]-specgraph。 -->

### 功能描述

SpecGraph：spec/edge 模型、load/save、dry_run_merge、combined_specgraph、resolve_chunk_uri、@ref 建边、export_dot；baseline + per-version 分文件。

<!-- @id:[FSD]-ait-specgraph:deps -->
## deps

<!-- @summary: 依赖查询：返回某 chunk 的 depends_on / 上游关系。 details [TDD]-deps。 -->

### 功能描述

依赖查询：返回某 chunk 的 depends_on / 上游关系。

<!-- @id:[FSD]-ait-specgraph:impact -->
## impact

<!-- @summary: 影响查询：返回改动某 chunk 的下游影响面。 details [TDD]-impact。 -->

### 功能描述

影响查询：返回改动某 chunk 的下游影响面。
