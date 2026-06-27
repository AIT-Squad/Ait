<!-- @id:[FSD]-ait-prd -->
## prd FSD

<!-- @summary: 旧模型 PRD 生命周期域。details 到对应 TDD（一文件一映射）。 -->

### 功能范围

ait prd：四段结构 PRD、req 草稿、confirm 写工作区、commit 锁定。

<!-- @id:[FSD]-ait-prd:prd_manager -->
## prd_manager

<!-- @summary: PrdManager：create/save_draft/confirm/commit/show；四段结构与 summary 必需校验；req 草稿持久化；co details [TDD]-prd_manager。 -->

### 功能描述

PrdManager：create/save_draft/confirm/commit/show；四段结构与 summary 必需校验；req 草稿持久化；commit 锁定写保护。
