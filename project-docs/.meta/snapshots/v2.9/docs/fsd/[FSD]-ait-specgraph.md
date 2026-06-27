<!-- @id:[FSD]-ait-specgraph -->
## specgraph FSD

### 功能范围

ait specgraph/deps/impact：关系图、建边、依赖与影响、dot 导出、新模型图校验。

<!-- @id:[FSD]-ait-specgraph:specgraph -->
## specgraph

### 功能描述

SpecGraph：spec/edge 模型、load/save、dry_run_merge、combined_specgraph、resolve_chunk_uri、@ref 建边、export_dot；baseline + per-version 分文件。

<!-- @id:[FSD]-ait-specgraph:deps -->
## deps

### 功能描述

依赖查询：返回某 chunk 的 depends_on / 上游关系。

<!-- @id:[FSD]-ait-specgraph:impact -->
## impact

### 功能描述

影响查询：返回改动某 chunk 的下游影响面。
