<!-- @id:[TDD]-context_assembler -->
## context_assembler TDD
```yaml
target_file: skill/ait/ait/context_assembler.py
```
### 技术栈
Python 3.10+；依赖 `specgraph`(combined_specgraph)、`index_manager`、`chunk_parser`。
### 数据结构
`@dataclass ContextSlice{chunk_id,file,content,role}`；`@dataclass AssembledContext{...; to_dict()}`。
### 代码结构
- `assemble(target_id, *, scenario="prd-to-impl", focus=False, include_deps=False)->AssembledContext`：L1=`_locate_chunk`(目标)；focus 则只 L1；否则按 scenario 取 L2：`_impl_related_to_prd`(prd→impl)/`_prd_related_to_impl`(impl→prd)/`_deps_related_to_chunk`(specgraph 依赖)。
- `_locate_chunk/_read_chunk_from`。
### 单元测试要求
`tests/test_prd_impl_context.py`：L1-only(focus)、prd-to-impl 取 impl、include_deps 取 specgraph 依赖。pytest。
