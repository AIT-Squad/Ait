<!-- @id:[FSD]-ait-new_model -->
## new_model FSD

### 功能范围

新模型 PRD/FSD/TDD 文档与代码生成上下文。创建文档、显式建关系边、图合法性与 target_file 唯一性校验、**六不变式约束（写时局部门禁＋confirm 全局门禁的校验内核）**、codegen 上溯组装。

### 交互契约

- 创建：`create_prd/create_fsd/create_tdd`（写版本工作区、ensure 版本 meta；TDD 必含 target_file，**写入前按归一化路径做制品唯一属主门禁**）。
- 建边：`add_edge(src,dst,rel)` rel∈{decomposes,details,depends_on}；**落盘前经 `check_edge_write` 局部门禁——幽灵端点/TDD 第二父/PRD 第二 FSD 拒绝，零落盘可重试**。
- codegen：`prepare_codegen(version,tdd) -> CodegenBundle`（target_file + 上溯 FSD/PRD + 依赖契约；组合视图 chunk_id 世界，modify 中的 chunk 上下文完整）。
- 校验：`validate_prd_fsd_tdd_graph` + `validate_target_file_uniqueness`（归一化）+ **`validate_invariants`（六不变式：PRD↔1FSD、TDD↔1FSD/1制品、制品↔1TDD、关联经 chunk、无孤儿、可追溯；另检树关系环——depends_on 环可诊断不拦）——供 version confirm 全局门禁消费**。

<!-- @id:[FSD]-ait-new_model:new_model_manager -->
## new_model_manager
### 功能描述
NewModelManager：create_prd/fsd/tdd（_create_document：解析→ensure 版本→write_version_file→注册 chunk→sync_specgraph；create_tdd 写前做归一化 target_file 唯一属主门禁）、add_edge（写前 check_edge_write 局部门禁，拒绝＝零落盘可重试）、prepare_codegen（组合视图上溯+依赖+target_file，无版本回退 baseline）、collect_tdd_target_files。详见 [TDD]-new_model_manager。

<!-- @id:[FSD]-ait-new_model:new_model_validator -->
## new_model_validator
### 功能描述
图合法性（decomposes/details/depends_on 类型与根-split 规则、FSD 不混子）+ target_file 唯一性（归一化后 DUPLICATE_TARGET_FILE）+ **六不变式套件 validate_invariants（吃 CombinedView：PRD_FSD_LINK_NOT_UNIQUE/TDD_MULTI_PARENT/DUPLICATE_TARGET_FILE/MISSING_ENDPOINT/ORPHAN_CHUNK/TRACE_BROKEN＋SPEC_CYCLE〔仅 decomposes/details 树关系；depends_on 环可诊断不作门禁〕；孤儿与追溯遍历含 id 结构通道；无新模型节点 vacuous pass）+ 写时局部门禁 check_edge_write**。纯函数不读盘。详见 [TDD]-new_model_validator。
