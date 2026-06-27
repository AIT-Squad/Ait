<!-- @id:[FSD]-ait-lint -->
## lint FSD
### 功能范围
旧模型 PRD/impl 格式与结构校验（与新模型图校验 validate-new-model 分离）：校验框架 + 四段结构/派生命名/@extract 边界。
### 交互契约
`scan_prd_text/scan_impl_text`(检出)、`fix_prd_text`(自动修)、`validate_parsed_file`、`validate_derived_name/validate_task_id`、`is_version_scope`。

<!-- @id:[FSD]-ait-lint:validator -->
## validator
### 功能描述
校验框架：ValidationIssue/ValidationError(severity E1/E2)、chunk ID 格式、非空、唯一性、@ref 目标存在。详见 [TDD]-validator。

<!-- @id:[FSD]-ait-lint:format_validator -->
## format_validator
### 功能描述
PRD 四段结构、impl 结构、派生命名(DERIVED_NAME)、task id、@extract/code-fence 边界校验；fix_prd_text 英文标题→中文四段。详见 [TDD]-format_validator。
