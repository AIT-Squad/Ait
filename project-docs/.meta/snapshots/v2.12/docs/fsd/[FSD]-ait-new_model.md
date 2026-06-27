<!-- @id:[FSD]-ait-new_model -->
## new_model FSD

### 功能范围

新模型 PRD/FSD/TDD 文档与代码生成上下文。创建文档、显式建关系边、图合法性与 target_file 唯一性校验、codegen 上溯组装。

### 交互契约

- 创建：`create_prd/create_fsd/create_tdd`（写版本工作区、ensure 版本 meta；TDD 必含 target_file）。
- 建边：`add_edge(src,dst,rel)` rel∈{decomposes,details,depends_on}。
- codegen：`prepare_codegen(version,tdd) -> CodegenBundle`（target_file + 上溯 FSD/PRD + 依赖契约）。
- 校验：`validate_prd_fsd_tdd_graph` + `validate_target_file_uniqueness`。

<!-- @id:[FSD]-ait-new_model:new_model_manager -->
## new_model_manager
### 功能描述
NewModelManager：create_prd/fsd/tdd（_create_document：解析→ensure 版本→write_version_file→注册 chunk→sync_specgraph）、add_edge、prepare_codegen（上溯+依赖+target_file，无版本回退 baseline）、collect_tdd_target_files。详见 [TDD]-new_model_manager。

<!-- @id:[FSD]-ait-new_model:new_model_validator -->
## new_model_validator
### 功能描述
图合法性（decomposes/details/depends_on 类型与根-split 规则、FSD 不混子）+ target_file 唯一性（DUPLICATE_TARGET_FILE）。详见 [TDD]-new_model_validator。
