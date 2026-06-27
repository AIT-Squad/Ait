<!-- @id:[FSD]-ait-init -->
## init FSD

### 功能范围

ait init：旧 global 基线 + 新模型骨架、wrapper 生成、增量补全与幂等。

<!-- @id:[FSD]-ait-init:init_manager -->
## init_manager

### 功能描述

InitManager：fresh/incomplete/ready 状态判定；full/incremental/new-model bootstrap；生成 docs/global 或 docs/prd,fsd,tdd 根 + decomposes 边；写 .meta/config.yaml 与项目 wrapper。
