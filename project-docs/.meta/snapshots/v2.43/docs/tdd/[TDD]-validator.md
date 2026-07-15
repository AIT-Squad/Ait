<!-- @id:[TDD]-validator -->
## validator TDD
```yaml
target_file: skill/ait/ait/validator.py
```
### 技术栈
Python 3.10+；依赖 `chunk_parser`(Chunk/ParsedFile)。
### 数据结构
`@dataclass ValidationIssue{severity("E1"/"E2"),code,message,chunk_id?,...}`；`ValidationError(Exception){issues:list, details}`。
### 代码结构
- `validate_id_format(chunk_id)->Issue|None`(小写短横线/bracket 前缀，否则 ID_FORMAT)。
- `validate_chunk_nonempty(chunk)->Issue|None`。
- `validate_unique_ids(parsed)->list[Issue]`(文件内重复 @id)。
- `validate_baseline_id_unique(...)`。
- `validate_ref_target(...)`(@ref 目标 chunk 存在)。
- `validate_parsed_file(...)->list[Issue]`(综合)。
- `raise_if_e1(issues)`(有 E1 则 raise ValidationError)。
### 单元测试要求
`tests/`(validator 相关)：ID 格式、唯一性、ref 目标、E1 抛错。pytest。
