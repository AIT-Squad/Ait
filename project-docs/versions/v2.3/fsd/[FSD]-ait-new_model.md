<!-- @id:[FSD]-ait-new_model -->
## new_model FSD

<!-- @summary: 新模型 PRD/FSD/TDD 域。details 到对应 TDD（一文件一映射）。 -->

### 功能范围

ait prdv2/fsd/tdd/codegen：新模型文档、显式建边、图校验、codegen 上下文。

<!-- @id:[FSD]-ait-new_model:new_model_manager -->
## new_model_manager

<!-- @summary: NewModelManager：create_prd/fsd/tdd（写版本工作区、ensure 版本 meta）、add_edge（decomposes/de details [TDD]-new_model_manager。 -->

### 功能描述

NewModelManager：create_prd/fsd/tdd（写版本工作区、ensure 版本 meta）、add_edge（decomposes/details/depends_on）、prepare_codegen（上溯 FSD/PRD + 依赖契约 + target_file，无版本回退 baseline）、collect_tdd_target_files。

<!-- @id:[FSD]-ait-new_model:new_model_validator -->
## new_model_validator

<!-- @summary: validate_prd_fsd_tdd_graph：关系合法性（decomposes PRD/FSD→FSD、details 叶FSD→TDD、depends details [TDD]-new_model_validator。 -->

### 功能描述

validate_prd_fsd_tdd_graph：关系合法性（decomposes PRD/FSD→FSD、details 叶FSD→TDD、depends_on 同父兄弟）、FSD 不混 FSD/TDD 子；validate_target_file_uniqueness：DUPLICATE_TARGET_FILE。
