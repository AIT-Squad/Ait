<!-- @id:[FSD]-ait-impl -->
## impl FSD

### 功能范围

ait impl：1 PRD→N impl、@extract、@ref implements、pre-merge 校验、inherit、lock。

<!-- @id:[FSD]-ait-impl:impl_manager -->
## impl_manager

### 功能描述

ImplManager：create（自动注入 @ref implements）、commit（pre-merge：成环/重复 @id/@extract 目标）、inherit、lock；@extract 标记动态 global 片段。
