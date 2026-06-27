<!-- @id:[FSD]-ait-init -->
## init FSD
### 功能范围
`ait init` 项目初始化：旧 global 基线 bootstrap、新模型 prd/fsd/tdd 骨架(--new-model)、wrapper/config 生成、增量补全与幂等、--refresh-wrapper。
### 交互契约
`run(*,check_only,skip,new_model,project_name) -> InitResult`；`refresh_wrapper()`。
<!-- @id:[FSD]-ait-init:init_manager -->
## init_manager
### 功能描述
InitManager：状态判定(fresh/incomplete/ready)、full/incremental/new-model bootstrap、生成 docs/global 或 docs/{prd,fsd,tdd} 根 + decomposes 边、写 .meta/config.yaml 与项目 wrapper。详见 [TDD]-init_manager。
