<!-- @id:[FSD]-ait-impl -->
## impl FSD

<!-- @summary: 旧模型 impl 生命周期域。details 到对应 TDD（一文件一映射）。 -->

### 功能范围

ait impl：1 PRD→N impl、@extract、@ref implements、pre-merge 校验、inherit、lock。

<!-- @id:[FSD]-ait-impl:impl_manager -->
## impl_manager

<!-- @summary: ImplManager：create（自动注入 @ref implements）、commit（pre-merge：成环/重复 @id/@extract 目标） details [TDD]-impl_manager。 -->

### 功能描述

ImplManager：create（自动注入 @ref implements）、commit（pre-merge：成环/重复 @id/@extract 目标）、inherit、lock；@extract 标记动态 global 片段。
