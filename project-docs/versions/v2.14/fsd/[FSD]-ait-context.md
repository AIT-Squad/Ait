<!-- @id:[FSD]-ait-context -->
## context FSD
### 功能范围
旧模型聚焦上下文装配：L1 目标 chunk + L2 specgraph 依赖（prd-to-impl / impl-edit 场景）。
### 交互契约
`assemble(target_id, scenario, focus, include_deps) -> AssembledContext`。
<!-- @id:[FSD]-ait-context:context_assembler -->
## context_assembler
### 功能描述
ContextAssembler.assemble：定位目标 chunk(L1) + 按场景取 impl↔prd/deps(L2)；ContextSlice/AssembledContext.to_dict。详见 [TDD]-context_assembler。
