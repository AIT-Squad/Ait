<!-- @id:[FSD]-ait-impl -->
## impl FSD
### 功能范围
旧模型 impl 生命周期：1 PRD→N impl、@extract 标记动态 global、@ref implements 自动注入、pre-merge 校验、inherit、lock。
### 交互契约
`create(prd_chunk) / commit / lock / inherit / show`。
<!-- @id:[FSD]-ait-impl:impl_manager -->
## impl_manager
### 功能描述
ImplManager：create(注入 @ref implements、追加写 impl 文件)、commit(pre-merge:成环/重复 @id/@extract、summary/format ready)、lock(推进 phase)、inherit(从 baseline 复制 impl 进版本)、覆盖校验。详见 [TDD]-impl_manager。
