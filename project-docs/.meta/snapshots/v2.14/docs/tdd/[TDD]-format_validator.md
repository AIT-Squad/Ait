<!-- @id:[TDD]-format_validator -->
## format_validator TDD
```yaml
target_file: skill/ait/ait/format_validator.py
```
### 技术栈
Python 3.10+；`re`；依赖 `chunk_parser`(Chunk)。
### 数据结构
`@dataclass FormatViolation{code,message,chunk_id?,line?,fixable:bool,fix_hint?}`。
### 代码结构
- `validate_prd_chunk(chunk)`：四段结构(概述/业务规则/验收标准/边界与非目标)缺失/顺序/英文标题→违规。
- `validate_impl_chunk(chunk,*,full_text)`：impl 结构 + @extract 配对。
- `validate_chunk_id` / `validate_task_id` / `validate_derived_name(impl_id, prd_id...)`（impl/task 必须从 PRD chunk 派生，否则 DERIVED_NAME_VIOLATION，给 accepted 前缀）。
- `scan_prd_text/scan_impl_text(text,file)->[FormatViolation]`。
- `fix_prd_text(text)->(new_text,changed)`(英文段标题→中文四段，仅可修项)。
- 辅助：`violation_to_issue/violations_to_details/is_version_scope/_chunk_headings/_code_fence_ranges/_accepted_impl_prefixes/_strip_prd_prefix/_normalize`。
### 单元测试要求
`tests/`(format 相关)：四段缺失、派生命名违规、fix 英→中、code-fence 内不误判。pytest。
