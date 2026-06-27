<!-- @id:[TDD]-new_model_validator -->
## new_model_validator TDD

```yaml
target_file: skill/ait/ait/new_model_validator.py
```

### 技术栈
Python 3.10+；依赖 `specgraph`(Edge/Spec/SpecGraph)。纯函数校验。

### 常量
`ALLOWED_RELS={decomposes,details,depends_on}`；`NEW_MODEL_TYPES={prd,fsd,tdd}`；`NEW_MODEL_PREFIXES=("[PRD]-","[FSD]-","[TDD]-")`。

### 数据结构
`@dataclass(frozen=True) NewModelViolation{code,message,chunk_id?,file?,rel?,src?,dst?}`。

### 代码结构
- `validate_prd_fsd_tdd_graph(graph)->list[NewModelViolation]`：遍历 edges；端点缺失且 rel∈ALLOWED→`MISSING_ENDPOINT`；非新模型 spec 跳过；rel 不在 ALLOWED→`UNSUPPORTED_RELATION`；按 rel 分派 `_validate_decomposes/_validate_details/_validate_depends_on`；累积 `child_kinds_by_parent`（internal split 的 fsd/tdd 子类型）；最后 `{fsd,tdd}` 同父 → `FSD_MIXED_CHILDREN`。
- `_validate_decomposes(edge,src,dst)`：prd→fsd 须 root→root（否则 `INVALID_PRD_DECOMPOSES`）；fsd→fsd 须 internal_split→root（否则 `INVALID_FSD_DECOMPOSES`）；其余 `INVALID_DECOMPOSES_TYPES`。
- `_validate_details`：须 fsd internal_split → tdd root，否则 `INVALID_DETAILS`。
- `_validate_depends_on`：两端须 fsd（否则 `INVALID_DEPENDS_ON_TYPES`）、须 internal_split（否则 `DEPENDS_ON_ROOT_CHUNK`）、同父（否则 `DEPENDS_ON_CROSS_LEVEL`）。
- `validate_target_file_uniqueness(entries:list[(chunk_id,file,target_file)])`：按 target_file 分组，>1 owner → `DUPLICATE_TARGET_FILE`（列冲突 chunk id）。
- `violations_to_details(violations)->list[dict]`。
- 判定辅助：`_is_new_model_spec`(type∈NEW_MODEL_TYPES 且 chunk_id 前缀)、`_is_root_chunk`(无 ":" 且 file_stem==chunk_id)、`_is_internal_split`(fsd 且含 ":" 且 parent==file_stem)、`_parent_chunk_id/_file_stem/_find_spec_by_chunk_id/_violation`。

### 错误码
`MISSING_ENDPOINT`、`UNSUPPORTED_RELATION`、`INVALID_PRD_DECOMPOSES`、`INVALID_FSD_DECOMPOSES`、`INVALID_DECOMPOSES_TYPES`、`INVALID_DETAILS`、`INVALID_DEPENDS_ON_TYPES`、`DEPENDS_ON_ROOT_CHUNK`、`DEPENDS_ON_CROSS_LEVEL`、`FSD_MIXED_CHILDREN`、`DUPLICATE_TARGET_FILE`。

### 单元测试要求
`tests/test_new_model_validator.py`：各关系合法/非法、FSD 混子、depends_on 跨级、target_file 重复与不重复。pytest。
