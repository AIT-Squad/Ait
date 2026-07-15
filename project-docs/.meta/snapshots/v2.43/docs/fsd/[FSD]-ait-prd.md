<!-- @id:[FSD]-ait-prd -->
## prd FSD
### 功能范围
旧模型 PRD(`ait prdv1`)生命周期：req 草稿、四段结构、confirm 写工作区、commit 锁定、candidate 决策。
### 交互契约
`create(title) / save_draft / resolve_candidates / confirm / commit`；req 持久化。

<!-- @id:[FSD]-ait-prd:prd_manager -->
## prd_manager
### 功能描述
PrdManager：create(建 req + 自动建版本)、save_draft、resolve_candidates(skill 产出的候选决策落库)、四段+summary 校验、confirm/commit 锁定；slugify 文件名。详见 [TDD]-prd_manager。
