<!-- @id:[FSD]-ait-indexing -->
## indexing FSD

<!-- @summary: 索引重建与迁移域。details 到对应 TDD（一文件一映射）。 -->

### 功能范围

ait reindex/baseline-summary/migrate：索引重建、摘要、历史迁移。

<!-- @id:[FSD]-ait-indexing:index_manager -->
## index_manager

<!-- @summary: IndexManager：baseline/version chunks-index 加载/保存/重建（rebuild_baseline）、query_base details [TDD]-index_manager。 -->

### 功能描述

IndexManager：baseline/version chunks-index 加载/保存/重建（rebuild_baseline）、query_baseline/query_version、summary 索引。

<!-- @id:[FSD]-ait-indexing:migrations -->
## migrations

<!-- @summary: 一次性数据迁移：block→chunk 等历史 schema 迁移（migrate-block-to-chunk）。 details [TDD]-migrations。 -->

### 功能描述

一次性数据迁移：block→chunk 等历史 schema 迁移（migrate-block-to-chunk）。
